"""Lazy headshot generation for Person entities.

Flow (idempotent; called from the /api/entities/{key}/headshot route):

1. Look up the Person entity in Neo4j by normalized ``key``. If ``headshot_url``
   is already set on the node, return it and skip the rest.
2. Find the FIRST Segment that ``MENTIONS`` this Person, ordered by video +
   start time, so the frame we use is "where they are identified". Pick the
   earliest moment — it tends to be a clean establishing shot rather than
   motion-blurred in-the-action footage.
3. Resolve the Video's HLS playback URL (via TwelveLabs), download one frame
   at that timestamp with ffmpeg, save it under a temp path.
4. Send the frame to the OpenAI Images Edits endpoint with a "professional
   headshot" prompt; the model returns a polished portrait that still
   resembles the original person.
5. Write the result PNG to ``static/headshots/<key>.png`` (relative path is
   stable, survives container restarts), persist the public URL on the Entity
   node, and return the URL.

The module is deliberately small and self-contained; it has no opinion on
how the front-end chooses to render the URL.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


class HeadshotError(RuntimeError):
    """Raised for any headshot-generation failure the route should surface as 5xx."""


# ---------------------------------------------------------------------------
# Capability probing
# ---------------------------------------------------------------------------

_FFMPEG_PATH: str | None = None
_FFMPEG_PROBED: bool = False


def ffmpeg_available() -> str | None:
    """Return the path to ffmpeg if it's installed, else None.

    Probed once per process; the result is cached. Used by the route to
    fail fast with a 503 instead of hanging on a missing tool when the user
    clicks a Person node on the frontend.
    """
    global _FFMPEG_PATH, _FFMPEG_PROBED
    if _FFMPEG_PROBED:
        return _FFMPEG_PATH
    _FFMPEG_PROBED = True
    path = shutil.which("ffmpeg")
    _FFMPEG_PATH = path
    if not path:
        logger.warning("ffmpeg not found on PATH — /api/entities/{key}/headshot "
                       "will return 503 until ffmpeg is installed.")
    return path


# ---------------------------------------------------------------------------
# Neo4j: locate the person + first segment mentioning them
# ---------------------------------------------------------------------------

async def _person_with_first_segment(entity_key: str) -> dict | None:
    """Return {name, video_id, tl_index_id, t_start_sec, video_url} or None.

    ``video_url`` is the HLS playback URL from TwelveLabs (or, for the
    external URL case, the original YouTube/public URL we stored on the
    Video node); ffmpeg needs *something* it can stream. If the video has
    no resolvable URL we treat that as "no headshot possible" and the
    caller returns 502.
    """
    from app.context_graph_client import execute_cypher

    rows = await execute_cypher(
        """
        MATCH (e:Entity {key: $key})
        WHERE (e.domain IS NULL OR e.domain = $domain)
          AND toLower(coalesce(e.type, '')) = 'person'
        OPTIONAL MATCH (e)<-[m:MENTIONS]-(s:Segment)-[:HAS_SEGMENT]->(v:Video)
        WITH e, v, s ORDER BY coalesce(v.title, v.id), coalesce(s.start_sec, 0)
        WITH e, v, collect({start_sec: s.start_sec, segment_id: s.id, video_id: v.id,
                             tl_index_id: v.tl_index_id, video_url: v.url}) AS hits
        RETURN e.key AS key, e.name AS name, e.headshot_url AS headshot_url,
               hits[0] AS first
        """,
        {"key": entity_key, "domain": settings.domain_id},
        collect=False,
    )
    if not rows:
        return None
    row = rows[0]
    first = row.get("first") or {}
    return {
        "key": row.get("key"),
        "name": row.get("name"),
        "headshot_url": row.get("headshot_url"),
        "video_id": first.get("video_id"),
        "tl_index_id": first.get("tl_index_id"),
        "t_start_sec": first.get("start_sec"),
        "video_url": first.get("video_url"),
    }


# ---------------------------------------------------------------------------
# Frame extraction (ffmpeg over the HLS playback)
# ---------------------------------------------------------------------------

def _extract_frame(video_url: str, t_sec: float | None,
                   dest_png: Path, ffmpeg: str) -> None:
    """Run ffmpeg to pull a single frame from ``video_url`` into ``dest_png``.

    HLS playlists can take a few seconds to start streaming, and the model's
    quality is fine regardless of the exact second picked, so the route
    falls back to "near the start" when ``t_sec`` is None.
    """
    dest_png.parent.mkdir(parents=True, exist_ok=True)
    # Use `-ss` before `-i` for a fast (keyframe) seek; `-frames:v 1` writes a
    # single image and lets ffmpeg exit on its own. `-y` overwrites in case
    # a stale file is hanging around in the temp dir.
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{max(0.0, (t_sec or 0)):.2f}",
        "-i", video_url,
        "-frames:v", "1",
        str(dest_png),
    ]
    try:
        subprocess.run(cmd, check=True, timeout=45)
    except subprocess.TimeoutExpired as e:
        raise HeadshotError(f"ffmpeg timed out extracting {video_url}") from e
    except subprocess.CalledProcessError as e:
        raise HeadshotError(
            f"ffmpeg failed on {video_url} (rc={e.returncode}); the URL may "
            f"not be an HLS URL the local ffmpeg can decode."
        ) from e


# ---------------------------------------------------------------------------
# OpenAI image edit -> professional headshot
# ---------------------------------------------------------------------------

def _generate_headshot_png(frame_png: Path, person_name: str) -> bytes:
    """Call the OpenAI Images Edit endpoint and return the resulting PNG bytes."""
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key or None)
    prompt = (
        f"Subject's name: {person_name}. " if person_name else ""
    ) + settings.headshot_prompt

    with open(frame_png, "rb") as fh:
        result = client.images.edit(
            model=settings.headshot_openai_model,
            image=fh,
            prompt=prompt,
            size="1024x1024",
        )
    # `b64_json` is the canonical portable payload for storage; the SDK
    # also exposes `url` for hosted previews. Decode either.
    import base64
    item = result.data[0] if getattr(result, "data", None) else None
    if item is None:
        raise HeadshotError("OpenAI returned no image data")
    if getattr(item, "b64_json", None):
        return base64.b64decode(item.b64_json)
    if getattr(item, "url", None):
        import requests
        resp = requests.get(item.url, timeout=30)
        resp.raise_for_status()
        return resp.content
    raise HeadshotError("OpenAI image response had neither b64_json nor url")


# ---------------------------------------------------------------------------
# Disk path helpers
# ---------------------------------------------------------------------------

def _static_root() -> Path:
    """Resolve the headshot static directory absolute path."""
    return Path(settings.headshot_static_dir).resolve()


def _entity_path(entity_key: str) -> Path:
    """Where on disk to keep the PNG for one entity."""
    # Hex entity keys can include unsafe chars; sanitize while keeping
    # them human-readable in logs.
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in entity_key)
    return _static_root() / f"{safe}.png"


def _public_url_for(path: Path) -> str:
    """Build the public URL the front-end will fetch."""
    rel = path.resolve().relative_to(_static_root().parent)
    return f"{settings.headshot_url_prefix.rstrip('/')}/{path.name}"


# ---------------------------------------------------------------------------
# Persistence: write PNG to disk, save URL on Entity
# ---------------------------------------------------------------------------

async def _set_entity_headshot_url(entity_key: str, url: str | None) -> None:
    from app.context_graph_client import execute_cypher

    await execute_cypher(
        "MATCH (e:Entity {key: $key}) "
        "WHERE e.domain IS NULL OR e.domain = $domain "
        "SET e.headshot_url = $url",
        {"key": entity_key, "url": url, "domain": settings.domain_id},
        collect=False,
    )


# ---------------------------------------------------------------------------
# Public entry point used by the route
# ---------------------------------------------------------------------------

async def ensure_headshot(entity_key: str, *,
                          force: bool = False,
                          on_update=None) -> dict:
    """Return ``{url, cached}`` for the entity's headshot, generating if needed.

    ``force=True`` regenerates even when ``Entity.headshot_url`` is set; useful
    for tests/CLI, not for the user-facing endpoint.
    """
    p = await _person_with_first_segment(entity_key)
    if p is None:
        raise HeadshotError(f"No Person entity with key {entity_key!r}")
    if p.get("headshot_url") and not force:
        return {"url": p["headshot_url"], "cached": True}

    ffmpeg = ffmpeg_available()
    if not ffmpeg:
        raise HeadshotError(
            "ffmpeg is required to extract a representative frame and is not "
            "installed on this server. Install ffmpeg to enable headshots."
        )

    video_url = p.get("video_url")
    if not video_url:
        raise HeadshotError(
            f"Video {p.get('video_id')!r} has no playable URL on file; cannot "
            f"extract a frame for {p.get('name')!r}."
        )

    def _progress(msg: str):
        logger.info("  headshot: %s", msg)
        if on_update:
            on_update(msg)

    final_path = _entity_path(entity_key)
    if final_path.exists() and not force:
        url = _public_url_for(final_path)
        await _set_entity_headshot_url(entity_key, url)
        return {"url": url, "cached": True}

    with tempfile.TemporaryDirectory(prefix="headshot-") as tmp:
        tmp_dir = Path(tmp)
        frame_png = tmp_dir / "frame.png"

        _progress("extracting a representative frame")
        await asyncio.to_thread(_extract_frame, video_url,
                                 p.get("t_start_sec"), frame_png, ffmpeg)

        _progress("asking OpenAI to render a professional headshot")
        png_bytes = await asyncio.to_thread(
            _generate_headshot_png, frame_png, p.get("name") or ""
        )

        # Validate it's a real PNG before handing the URL back.
        from PIL import Image
        import io
        verified = Image.open(io.BytesIO(png_bytes))
        verified.verify()
        img = Image.open(io.BytesIO(png_bytes))  # re-open, verify() invalidates
        img.load()  # fully decode so save() doesn't trigger lazy errors later

        final_path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic-ish write so a concurrent reader never sees a half-written file.
        tmp_png = final_path.with_suffix(final_path.suffix + f".{uuid.uuid4().hex}.tmp")
        img.save(tmp_png, format="PNG")
        os.replace(tmp_png, final_path)

    url = _public_url_for(final_path)
    await _set_entity_headshot_url(entity_key, url)
    _progress(f"saved {url}")
    return {"url": url, "cached": False}
