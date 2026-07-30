"""Offline smoke test for the Neo4j half of the ingest pipeline.

Exercises steps 4-5 of scripts/ingest.py (embed -> write) with synthetic data,
so the graph write path, the cross-video Entity/Topic MERGE, the temporal NEXT
chain and the vector index can be verified without an OpenAI or TwelveLabs key.

Writes two fake videos that share one entity under different spellings
("Tree" / "  tree  ") and asserts they collapse to a single node.

Run:  uv run --directory backend python scripts/smoke_graph.py
Wipe: uv run --directory backend python -c "import asyncio;from app.context_graph_client import reset_database;asyncio.run(reset_database())"
"""

from __future__ import annotations

import asyncio
import math
import random
import sys

sys.path.insert(0, ".")

from app.context_graph_client import connect_neo4j, close_neo4j, execute_cypher  # noqa: E402
from app.vector_client import ensure_segment_vector_index, segment_vector_search  # noqa: E402
from scripts.ingest import write_video  # noqa: E402

DIM = 512
FAILURES: list[str] = []


def fake_embedding(seed: int) -> list[float]:
    """A deterministic unit vector standing in for a Marengo embedding."""
    rng = random.Random(seed)
    v = [rng.uniform(-1.0, 1.0) for _ in range(DIM)]
    norm = math.sqrt(sum(x * x for x in v))
    return [x / norm for x in v]


def check(label: str, actual, expected) -> None:
    ok = actual == expected
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}: {actual!r}" + ("" if ok else f" (expected {expected!r})"))
    if not ok:
        FAILURES.append(label)


VIDEO_A = {
    "id": "smoke-video-a",
    "title": "smoke_clip_a",
    "url": "https://example.invalid/a.mp4",
    "duration_sec": 30.0,
    "summary": "A rabbit walks past a tree.",
    "tl_index_id": "smoke-index",
}
SEGMENTS_A = [
    {
        "start_sec": 0.0, "end_sec": 15.0,
        "summary": "A large rabbit emerges from a burrow beside a tall tree.",
        "on_screen_text": "", "transcript": "",
        "entities": [{"name": "Rabbit", "type": "object"}, {"name": "Tree", "type": "object"}],
        "topics": ["Nature"],
        "embedding": fake_embedding(1),
    },
    {
        "start_sec": 15.0, "end_sec": 30.0,
        "summary": "The rabbit stretches in the meadow while a butterfly flies by.",
        "on_screen_text": "", "transcript": "",
        "entities": [{"name": "Rabbit", "type": "object"}, {"name": "Butterfly", "type": "object"}],
        "topics": ["Nature", "Animation"],
        "embedding": fake_embedding(2),
    },
]

VIDEO_B = {
    "id": "smoke-video-b",
    "title": "smoke_clip_b",
    "url": "https://example.invalid/b.mp4",
    "duration_sec": 10.0,
    "summary": "A tree sways in the wind.",
    "tl_index_id": "smoke-index",
}
SEGMENTS_B = [
    {
        "start_sec": 0.0, "end_sec": 10.0,
        "summary": "A single tree stands on a hill under a blue sky.",
        "on_screen_text": "Big Buck Bunny", "transcript": "",
        # Deliberately different spelling/whitespace — must merge into "Tree".
        "entities": [{"name": "  tree  ", "type": "object"}, {"name": "Sky", "type": "object"}],
        "topics": ["  NATURE "],
        "embedding": fake_embedding(3),
    },
]


async def scalar(query: str, params: dict | None = None):
    rows = await execute_cypher(query, params, collect=False)
    return rows[0]["value"] if rows else None


async def main() -> None:
    await connect_neo4j()
    try:
        print("1. writing two synthetic videos ...")
        await write_video(VIDEO_A, SEGMENTS_A)
        await write_video(VIDEO_B, SEGMENTS_B)

        print("2. creating the vector index ...")
        await ensure_segment_vector_index(DIM)
        await execute_cypher("CALL db.awaitIndexes(60)", collect=False)

        print("3. structure checks")
        check("Video nodes", await scalar("MATCH (v:Video) WHERE v.id STARTS WITH 'smoke-' RETURN count(v) AS value"), 2)
        check("Segment nodes", await scalar("MATCH (s:Segment) WHERE s.video_id STARTS WITH 'smoke-' RETURN count(s) AS value"), 3)
        check("NEXT edges (video A only)", await scalar(
            "MATCH (:Segment {video_id:'smoke-video-a'})-[r:NEXT]->() RETURN count(r) AS value"), 1)
        check("segments carry a 512-dim embedding", await scalar(
            "MATCH (s:Segment) WHERE s.video_id STARTS WITH 'smoke-' AND size(s.embedding) = 512 RETURN count(s) AS value"), 3)

        print("4. cross-video MERGE checks")
        check("'Tree' is one node", await scalar(
            "MATCH (e:Entity {key:'tree'}) RETURN count(e) AS value"), 1)
        check("'Tree' spans 2 videos", await scalar(
            "MATCH (v:Video)-[:HAS_SEGMENT]->(:Segment)-[:MENTIONS]->(e:Entity {key:'tree'}) "
            "RETURN count(DISTINCT v) AS value"), 2)
        # key is normalized; the display name is whatever the most recent write set.
        check("'Tree' display name = last writer's spelling", await scalar(
            "MATCH (e:Entity {key:'tree'}) RETURN e.name AS value"), "tree")
        check("'Nature' topic is one node across both videos", await scalar(
            "MATCH (v:Video)-[:HAS_SEGMENT]->(:Segment)-[:ABOUT]->(t:Topic {key:'nature'}) "
            "RETURN count(DISTINCT v) AS value"), 2)

        rows = await execute_cypher(
            """
            MATCH (v:Video)-[:HAS_SEGMENT]->(:Segment)-[:MENTIONS]->(e:Entity)
            WHERE v.id STARTS WITH 'smoke-'
            WITH e, collect(DISTINCT v.title) AS videos, count(DISTINCT v) AS n
            WHERE n > 1
            RETURN e.name AS entity, e.type AS type, videos ORDER BY n DESC
            """,
            collect=False,
        )
        print(f"  shared entities: {rows}")
        check("exactly one shared entity", len(rows), 1)

        print("5. idempotent re-ingest check")
        await write_video(VIDEO_A, SEGMENTS_A)
        check("Segment count unchanged after re-write", await scalar(
            "MATCH (s:Segment) WHERE s.video_id STARTS WITH 'smoke-' RETURN count(s) AS value"), 3)

        print("6. vector search check")
        hits = await segment_vector_search(fake_embedding(3), top_k=3)
        top = hits[0]["s"]["id"] if hits else None
        check("nearest segment to embedding #3", top, "smoke-video-b#0")
    finally:
        await close_neo4j()

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s): {', '.join(FAILURES)}")
        sys.exit(1)
    print("ALL CHECKS PASSED — Neo4j write path, cross-video MERGE and vector index are working.")


if __name__ == "__main__":
    asyncio.run(main())
