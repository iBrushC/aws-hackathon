"""TwelveLabs integration — Marengo (embed/search) + Pegasus (analyze).

Pinned to the v1.2.x SDK surface (introspected, since the hosted docs lag):
  - client.indexes.create / list
  - client.tasks.create + client.tasks.wait_for_done   (index a video for search + analyze)
  - client.analyze(model_name=, video_id=, prompt=)     (Pegasus)
  - client.embed.create(model_name=, text=)             (Marengo text embedding)
  - client.search.query(index_id=, search_options=, query_text=, group_by=)

Response objects are fern-generated pydantic models; we navigate them with
``model_dump()`` and defensive extraction so minor schema drift doesn't break us.
"""

from __future__ import annotations

import logging
import os
import time
from functools import lru_cache
from typing import Any

from twelvelabs import TwelveLabs
from twelvelabs import IndexesCreateRequestModelsItem

from app.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_client() -> TwelveLabs:
    """Return a cached TwelveLabs client.

    The SDK auto-reads TWELVE_LABS_API_KEY from the environment; we also pass
    the configured key explicitly so it works even if only .env is populated.
    """
    api_key = settings.twelve_labs_api_key or None
    return TwelveLabs(api_key=api_key) if api_key else TwelveLabs()


# ---------------------------------------------------------------------------
# Extraction helpers — robust against fern schema drift
# ---------------------------------------------------------------------------

def _dump(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump()
        except Exception:
            pass
    return obj


def _deep_find_vector(obj: Any, min_len: int = 8) -> list[float] | None:
    """Find the first list of floats (an embedding) anywhere in a nested object."""
    d = _dump(obj)
    if isinstance(d, list):
        if len(d) >= min_len and all(isinstance(x, (int, float)) for x in d):
            return [float(x) for x in d]
        for item in d:
            v = _deep_find_vector(item, min_len)
            if v:
                return v
    elif isinstance(d, dict):
        # Prefer obviously-named fields first
        for key in ("float_", "float", "embedding", "values", "vector"):
            if key in d:
                v = _deep_find_vector(d[key], min_len)
                if v:
                    return v
        for v in d.values():
            found = _deep_find_vector(v, min_len)
            if found:
                return found
    return None


def _deep_find_text(obj: Any) -> str:
    """Pull the generated text out of a Pegasus analyze response."""
    d = _dump(obj)
    if isinstance(d, dict):
        for key in ("data", "text", "summary", "generated_text", "message"):
            val = d.get(key)
            if isinstance(val, str) and val.strip():
                return val
    if isinstance(d, str):
        return d
    return str(d)


def _getattr_any(obj: Any, *names: str):
    d = _dump(obj)
    if isinstance(d, dict):
        for n in names:
            if d.get(n) is not None:
                return d[n]
    for n in names:
        val = getattr(obj, n, None)
        if val is not None:
            return val
    return None


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------

def ensure_index() -> str:
    """Return an index id, creating (or finding by name) one if needed."""
    client = get_client()
    if settings.tl_index_id:
        return settings.tl_index_id

    # Find an existing index with the configured name
    try:
        for idx in client.indexes.list(index_name=settings.tl_index_name):
            idx_id = _getattr_any(idx, "id", "_id")
            if idx_id:
                logger.info("Reusing TwelveLabs index '%s' (%s)", settings.tl_index_name, idx_id)
                return str(idx_id)
    except Exception as e:
        logger.info("Index lookup failed (will create): %s", e)

    resp = client.indexes.create(
        index_name=settings.tl_index_name,
        models=[
            IndexesCreateRequestModelsItem(
                model_name=settings.marengo_model, model_options=["visual", "audio"]
            ),
            IndexesCreateRequestModelsItem(
                model_name=settings.pegasus_model, model_options=["visual", "audio"]
            ),
        ],
    )
    idx_id = str(_getattr_any(resp, "id", "_id"))
    logger.info("Created TwelveLabs index '%s' (%s)", settings.tl_index_name, idx_id)
    return idx_id


# ---------------------------------------------------------------------------
# Ingest (upload + index a video)
# ---------------------------------------------------------------------------

def upload_in_parts(index_id: str, video_file: str, on_update=None) -> dict:
    """Upload a large local video part by part, then index it.

    The multipart uploader splits the file, pushes the parts in parallel and
    retries them individually, so a dropped connection costs one part instead of
    a multi-gigabyte transfer. It also registers the file as an *asset*; the
    asset then has to be attached to the index explicitly, which the one-shot
    ``tasks.create`` path does for us.

    Returns the same shape as :func:`ingest_video`.
    """
    client = get_client()
    name = os.path.basename(video_file)
    size_mb = os.path.getsize(video_file) / 1e6

    reported = {"pct": -100.0}

    def _progress(p):
        pct = float(getattr(p, "percentage", 0.0) or 0.0)
        if pct - reported["pct"] < 10.0:
            return
        reported["pct"] = pct
        done = getattr(p, "completed_chunks", "?")
        total = getattr(p, "total_chunks", "?")
        logger.info("  upload %.0f%% (%s/%s parts)", pct, done, total)
        if on_update:
            on_update(f"uploading {pct:.0f}% ({done}/{total} parts)")

    logger.info("Uploading %s (%.0f MB) in parts ...", name, size_mb)
    result = client.multipart_upload.upload_file(
        video_file,
        filename=name,
        file_type="video",
        max_workers=settings.upload_chunk_workers,
        max_retries=3,
        progress_callback=_progress,
    )
    asset_id = str(_getattr_any(result, "asset_id", "id"))
    logger.info("Uploaded as asset %s — attaching to index %s", asset_id, index_id)

    created = client.indexes.indexed_assets.create(index_id, asset_id=asset_id)
    indexed_id = str(_getattr_any(created, "id", "_id") or asset_id)

    deadline = time.time() + settings.index_timeout_sec
    while time.time() < deadline:
        detail = _dump(client.indexes.indexed_assets.retrieve(index_id, indexed_id))
        status = detail.get("status") if isinstance(detail, dict) else None
        if on_update:
            on_update(status)
        if status == "ready":
            sm = (detail.get("system_metadata") or {}) if isinstance(detail, dict) else {}
            return {
                "task_id": None,
                "video_id": asset_id,
                "status": status,
                "duration_sec": sm.get("duration"),
                "filename": sm.get("filename") or name,
            }
        if status == "failed":
            raise RuntimeError(f"TwelveLabs failed to index {name}")
        time.sleep(5.0)
    raise TimeoutError(f"Indexing {name} exceeded {settings.index_timeout_sec}s")


def ingest_video(index_id: str, *, video_url: str | None = None,
                 video_file: str | None = None, on_update=None) -> dict:
    """Index a video from a public URL or a local file, blocking until done.

    Exactly one of ``video_url`` / ``video_file`` must be given. Local files at
    or above ``multipart_threshold_mb`` are uploaded in parts. Returns
    {video_id, status, duration_sec, filename}.
    """
    client = get_client()
    if video_file and os.path.getsize(video_file) >= settings.multipart_threshold_mb * 1_000_000:
        return upload_in_parts(index_id, video_file, on_update=on_update)
    if video_file:
        with open(video_file, "rb") as fh:
            task = client.tasks.create(
                index_id=index_id,
                video_file=(os.path.basename(video_file), fh),
            )
        source = video_file
    else:
        task = client.tasks.create(index_id=index_id, video_url=video_url)
        source = video_url
    task_id = str(_getattr_any(task, "id", "_id"))
    logger.info("TwelveLabs indexing task %s started for %s", task_id, source)

    def _cb(t):
        status = _getattr_any(t, "status")
        if on_update:
            on_update(status)

    done = client.tasks.wait_for_done(task_id=task_id, sleep_interval=5.0, callback=_cb)
    status = _getattr_any(done, "status")
    video_id = _getattr_any(done, "video_id")
    if not video_id:
        # Some SDK builds nest it under system metadata / hls
        d = _dump(done)
        if isinstance(d, dict):
            video_id = (
                (d.get("system_metadata") or {}).get("video_id")
                if isinstance(d.get("system_metadata"), dict) else None
            ) or d.get("video_id")
    meta = _dump(done)
    sys_meta = meta.get("system_metadata", {}) if isinstance(meta, dict) else {}
    return {
        "task_id": task_id,
        "video_id": str(video_id) if video_id else None,
        "status": status,
        "duration_sec": (sys_meta or {}).get("duration"),
        "filename": (sys_meta or {}).get("filename"),
    }


def get_video_meta(index_id: str, video_id: str) -> dict:
    """Fetch metadata for a video already indexed in TwelveLabs.

    Used to ingest an existing video by id (no re-upload). Returns
    {video_id, duration_sec, filename, url} where url is the HLS playback URL.
    """
    client = get_client()
    r = client.indexes.videos.retrieve(index_id=index_id, video_id=video_id)
    d = _dump(r)
    sm = (d.get("system_metadata") or {}) if isinstance(d, dict) else {}
    hls = (d.get("hls") or {}) if isinstance(d, dict) else {}
    return {
        "video_id": str(_getattr_any(r, "id", "_id") or video_id),
        "duration_sec": sm.get("duration"),
        "filename": sm.get("filename"),
        "url": hls.get("video_url"),
    }


# ---------------------------------------------------------------------------
# Analyze (Pegasus)
# ---------------------------------------------------------------------------

def analyze_video(video_id: str, prompt: str, temperature: float = 0.2,
                  max_tokens: int | None = None) -> str:
    """Run a Pegasus prompt over a whole video and return the generated text."""
    client = get_client()
    resp = client.analyze(
        model_name=settings.pegasus_model,
        video_id=video_id,
        prompt=prompt,
        temperature=temperature,
        max_tokens=max_tokens or settings.analysis_max_tokens,
    )
    return _deep_find_text(resp)


def analyze_video_window(asset_id: str, prompt: str, start_sec: float, end_sec: float,
                         temperature: float = 0.2, max_tokens: int | None = None) -> str:
    """Run a Pegasus prompt over ONE time window of a video.

    ``start_time``/``end_time`` are only accepted by the window-capable model
    (``pegasus1.5``), which takes a video *asset* rather than an index video id.
    The two ids are the same value in TwelveLabs today, so an already-indexed
    video can be re-analyzed window by window without re-uploading.

    Verified live: the timecodes in the returned prose are on the full video's
    clock, not relative to the window, so no offset correction is needed.
    """
    from twelvelabs.types.video_context import VideoContext_AssetId

    client = get_client()
    resp = client.analyze(
        model_name=settings.pegasus_window_model,
        video=VideoContext_AssetId(asset_id=asset_id),
        prompt=prompt,
        temperature=temperature,
        max_tokens=max_tokens or settings.analysis_max_tokens,
        start_time=start_sec,
        end_time=end_sec,
    )
    return _deep_find_text(resp)


# ---------------------------------------------------------------------------
# Embed (Marengo, text) — for the Neo4j vector index + query-time embedding
# ---------------------------------------------------------------------------

def embed_text(text: str) -> list[float]:
    """Embed text with Marengo. Returns the raw float vector."""
    client = get_client()
    resp = client.embed.create(model_name=settings.marengo_embed_model, text=text)
    vec = _deep_find_vector(resp)
    if not vec:
        raise RuntimeError(f"Could not extract embedding vector from response: {_dump(resp)!r:.400}")
    return vec


# ---------------------------------------------------------------------------
# Live search (Marengo, multimodal)
# ---------------------------------------------------------------------------

def search(
    index_id: str,
    query_text: str,
    search_options: list[str] | None = None,
    group_by: str = "clip",
    limit: int = 8,
) -> list[dict]:
    """Search indexed videos and return normalized clip hits."""
    client = get_client()
    pager = client.search.query(
        index_id=index_id,
        search_options=search_options or ["visual", "audio"],
        query_text=query_text,
        group_by=group_by,
        page_limit=limit,
    )
    hits: list[dict] = []
    for item in pager:
        d = _dump(item)
        if not isinstance(d, dict):
            continue
        # group_by=video items carry a nested clips list; group_by=clip are flat
        clips = d.get("clips")
        if isinstance(clips, list) and clips:
            for c in clips:
                hits.append(_normalize_clip(c, d.get("id") or d.get("video_id")))
        else:
            hits.append(_normalize_clip(d, d.get("video_id") or d.get("id")))
        if len(hits) >= limit:
            break
    return hits[:limit]


def _normalize_clip(c: dict, video_id: Any) -> dict:
    return {
        "video_id": str(c.get("video_id") or video_id or ""),
        "start_sec": c.get("start"),
        "end_sec": c.get("end"),
        "score": c.get("score"),
        "confidence": c.get("confidence"),
    }
