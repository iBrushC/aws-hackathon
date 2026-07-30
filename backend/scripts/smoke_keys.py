"""Cheap credential check for the two external APIs the pipeline needs.

Verifies that TWELVE_LABS_API_KEY and OPENAI_API_KEY in the repo-root .env
actually work, and that the model names in .env exist for this account —
before spending minutes on a real video ingest.

Prints no secrets.

Run:  uv run --directory backend python scripts/smoke_keys.py
"""

from __future__ import annotations

import sys

sys.path.insert(0, ".")

from app.config import settings  # noqa: E402

FAILURES: list[str] = []


def report(label: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(label)


def check_twelvelabs() -> None:
    print("TwelveLabs")
    if not settings.twelve_labs_api_key.startswith("tlk_"):
        report("key present", False, "TWELVE_LABS_API_KEY missing or not a tlk_ key")
        return
    report("key present", True, f"tlk_…{settings.twelve_labs_api_key[-4:]}")

    from app import twelvelabs_client as tl

    try:
        names = [getattr(i, "index_name", "?") for i in tl.get_client().indexes.list()]
        report("auth (indexes.list)", True, f"{len(names)} index(es) on the account")
    except Exception as e:
        report("auth (indexes.list)", False, f"{type(e).__name__}: {e}")
        return

    try:
        index_id = tl.ensure_index()
        report(f"index '{settings.tl_index_name}' ready", True, index_id)
    except Exception as e:
        report(f"index '{settings.tl_index_name}' ready", False,
               f"{type(e).__name__}: {e} (check MARENGO_MODEL / PEGASUS_MODEL)")
        return

    try:
        vec = tl.embed_text("a rabbit standing next to a tree")
        report(f"embed model '{settings.marengo_embed_model}'", True, f"{len(vec)}-dim vector")
    except Exception as e:
        report(f"embed model '{settings.marengo_embed_model}'", False, f"{type(e).__name__}: {e}")


def check_openai() -> None:
    print("OpenAI")
    if not settings.openai_api_key.startswith("sk-"):
        report("key present", False, "OPENAI_API_KEY missing or malformed")
        return
    report("key present", True, f"sk-…{settings.openai_api_key[-4:]}")

    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    try:
        available = {m.id for m in client.models.list()}
        report("auth (models.list)", True, f"{len(available)} models visible")
    except Exception as e:
        report("auth (models.list)", False, f"{type(e).__name__}: {e}")
        return

    for label, name in (("OPENAI_EXTRACTION_MODEL", settings.openai_extraction_model),
                        ("OPENAI_MODEL", settings.openai_model)):
        report(f"{label}='{name}' available", name in available,
               "" if name in available else "not in this account's model list")

    # The exact call ingest.py makes: structured output + reasoning effort.
    from scripts.ingest import VideoAnalysis, STRUCTURE_SYSTEM

    try:
        r = client.responses.parse(
            model=settings.openai_extraction_model,
            reasoning={"effort": settings.openai_reasoning_effort},
            input=[
                {"role": "system", "content": STRUCTURE_SYSTEM},
                {"role": "user", "content": "Video analysis:\n\n0-5s: A rabbit sits under a tree."},
            ],
            text_format=VideoAnalysis,
        )
        parsed = r.output_parsed
        report("structured extraction call", parsed is not None,
               f"{len(parsed.segments)} segment(s) parsed" if parsed else "no parsed output")
    except Exception as e:
        report("structured extraction call", False, f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    check_twelvelabs()
    print()
    check_openai()
    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s): {', '.join(FAILURES)}")
        sys.exit(1)
    print("ALL CREDENTIAL CHECKS PASSED — ready to ingest a real video.")
