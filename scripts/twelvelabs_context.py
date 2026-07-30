#!/usr/bin/env python3
"""Extract and display structured multimodal context from an example video."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from twelvelabs import TwelveLabs


POLL_INTERVAL_SECONDS = 10
TERMINAL_FAILURE_STATUSES = {"failed"}

CONTEXT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "visualContext": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "startSec": {"type": "number"},
                    "endSec": {"type": "number"},
                    "description": {"type": "string"},
                },
                "required": ["startSec", "endSec", "description"],
            },
        },
        "audioContext": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "startSec": {"type": "number"},
                    "endSec": {"type": "number"},
                    "description": {"type": "string"},
                },
                "required": ["startSec", "endSec", "description"],
            },
        },
        "speech": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "speaker": {"type": "string"},
                    "startSec": {"type": "number"},
                    "endSec": {"type": "number"},
                    "text": {"type": "string"},
                },
                "required": ["speaker", "startSec", "endSec", "text"],
            },
        },
        "onScreenText": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "startSec": {"type": "number"},
                    "endSec": {"type": "number"},
                    "text": {"type": "string"},
                },
                "required": ["startSec", "endSec", "text"],
            },
        },
        "people": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "role": {"type": "string"},
                    "evidence": {"type": "string"},
                },
                "required": ["name", "role", "evidence"],
            },
        },
        "topics": {"type": "array", "items": {"type": "string"}},
        "keyMoments": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "startSec": {"type": "number"},
                    "endSec": {"type": "number"},
                    "description": {"type": "string"},
                    "modalities": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["visual", "audio", "speech", "text"],
                        },
                    },
                },
                "required": [
                    "startSec",
                    "endSec",
                    "description",
                    "modalities",
                ],
            },
        },
    },
    "required": [
        "summary",
        "visualContext",
        "audioContext",
        "speech",
        "onScreenText",
        "people",
        "topics",
        "keyMoments",
    ],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload a video and show TwelveLabs-derived multimodal context."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--video", type=Path, help="Path to a local example video.")
    source.add_argument("--url", help="Public URL pointing directly to a video file.")
    parser.add_argument(
        "--store-id",
        default=os.getenv("TWELVELABS_KNOWLEDGE_STORE_ID"),
        help="Reuse an existing TwelveLabs knowledge store.",
    )
    parser.add_argument(
        "--store-name",
        default="conference-people-demo",
        help="Name used when creating a knowledge store.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional output JSON path. Defaults to outputs/context_<asset-id>.json.",
    )
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=POLL_INTERVAL_SECONDS,
        help="Seconds between asynchronous status checks.",
    )
    return parser.parse_args()


def require_api_key() -> str:
    api_key = os.getenv("TWELVELABS_API_KEY")
    if not api_key or api_key == "replace_with_your_api_key":
        raise SystemExit(
            "TWELVELABS_API_KEY is missing. Copy .env.example to .env and add "
            "your API key."
        )
    return api_key


def wait_for_asset(client: TwelveLabs, asset_id: str, poll_seconds: int) -> None:
    while True:
        asset = client.assets.retrieve(asset_id)
        print(f"Asset status: {asset.status}", flush=True)
        if asset.status == "ready":
            return
        if asset.status in TERMINAL_FAILURE_STATUSES:
            message = getattr(getattr(asset, "error", None), "message", "unknown error")
            raise RuntimeError(f"Asset processing failed: {message}")
        time.sleep(poll_seconds)


def wait_for_store_item(
    client: TwelveLabs,
    store_id: str,
    item_id: str,
    poll_seconds: int,
) -> None:
    while True:
        item = client.knowledge_store_items.retrieve(store_id, item_id)
        print(f"Knowledge store item status: {item.status}", flush=True)
        if item.status == "ready":
            return
        if item.status in TERMINAL_FAILURE_STATUSES:
            raise RuntimeError("Knowledge store indexing failed.")
        time.sleep(poll_seconds)


def upload_asset(client: TwelveLabs, args: argparse.Namespace) -> str:
    if args.video:
        video_path = args.video.expanduser().resolve()
        if not video_path.is_file():
            raise SystemExit(f"Example video not found: {video_path}")
        print(f"Uploading local video: {video_path}", flush=True)
        with video_path.open("rb") as video_file:
            asset = client.assets.create(
                method="direct",
                file=video_file,
                filename=video_path.name,
                enable_thumbnail=True,
            )
    else:
        print(f"Uploading video URL: {args.url}", flush=True)
        asset = client.assets.create(
            method="url",
            url=args.url,
            enable_thumbnail=True,
        )

    if not asset.id:
        raise RuntimeError("TwelveLabs did not return an asset ID.")
    print(f"Asset ID: {asset.id}", flush=True)
    return asset.id


def get_or_create_store(client: TwelveLabs, args: argparse.Namespace) -> str:
    if args.store_id:
        print(f"Using knowledge store: {args.store_id}", flush=True)
        return args.store_id

    store = client.knowledge_stores.create(
        name=args.store_name,
        description="Example conference video multimodal context demo.",
    )
    if not store.id:
        raise RuntimeError("TwelveLabs did not return a knowledge store ID.")
    print(f"Created knowledge store: {store.id}", flush=True)
    return store.id


def extract_context(client: TwelveLabs, store_id: str) -> dict[str, Any]:
    response = client.responses.create(
        knowledge_store_id=store_id,
        instructions=(
            "Use only evidence found in the indexed video. Do not guess a person's "
            "identity. If a name or role is not explicitly supported, use "
            "'Unknown' and explain the visible or spoken evidence."
        ),
        input=[
            {
                "type": "message",
                "role": "user",
                "content": (
                    "Analyze the video across all available modalities. Return a "
                    "concise overview of visual scenes, non-speech audio, spoken "
                    "content with speaker labels, on-screen text, people, topics, "
                    "and important timestamped moments."
                ),
            }
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "conference_multimodal_context",
                "description": "Structured multimodal context extracted from a video.",
                "schema_": CONTEXT_SCHEMA,
                "strict": True,
            }
        },
    )

    for output_item in response.output or []:
        if output_item.type != "message":
            continue
        for content_part in output_item.content or []:
            text = getattr(content_part, "text", None)
            if text:
                return json.loads(text)

    raise RuntimeError("TwelveLabs response did not contain structured output text.")


def main() -> int:
    load_dotenv()
    args = parse_args()
    client = TwelveLabs(api_key=require_api_key())

    asset_id = upload_asset(client, args)
    wait_for_asset(client, asset_id, args.poll_seconds)

    store_id = get_or_create_store(client, args)
    item = client.knowledge_store_items.create(
        store_id,
        asset_id=asset_id,
        asset_type="video",
    )
    if not item.id:
        raise RuntimeError("TwelveLabs did not return a knowledge store item ID.")
    print(f"Knowledge store item ID: {item.id}", flush=True)
    wait_for_store_item(client, store_id, item.id, args.poll_seconds)

    context = extract_context(client, store_id)
    rendered = json.dumps(context, indent=2, ensure_ascii=False)
    print("\nTwelveLabs-derived multimodal context:\n")
    print(rendered)

    output_path = args.output or Path("outputs") / f"context_{asset_id}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(f"{rendered}\n", encoding="utf-8")
    print(f"\nSaved context to: {output_path.resolve()}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        sys.exit(1)
