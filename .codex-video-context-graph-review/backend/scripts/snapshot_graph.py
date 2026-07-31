"""Save and restore the whole context graph as a JSON file.

The graph is meant to accumulate across working sessions, but everything in it
is one `make reset` or one `docker compose down -v` away from being gone — and
re-ingesting costs TwelveLabs minutes and OpenAI tokens for every video. A
snapshot is a cheap insurance policy against both.

Restoring is *additive*: nodes are MERGE'd on their natural key, so restoring an
old snapshot on top of a live graph brings the old videos back without
disturbing newer ones, and shared Entity/Topic nodes reconnect the two.

Segment embeddings are included, so vector search still works after a restore.

``--cypher`` writes the same graph as a plain .cypher script instead, for handing
to someone else: they paste it into their own Neo4j Browser and end up looking at
exactly this graph. Segment embeddings are left out of that form by default —
512 floats per segment dwarf everything else and are useless without the vector
index — so pass ``--with-embeddings`` if the recipient needs semantic search too.

Run:
  uv run --directory backend python scripts/snapshot_graph.py --save
  uv run --directory backend python scripts/snapshot_graph.py --cypher
  uv run --directory backend python scripts/snapshot_graph.py --list
  uv run --directory backend python scripts/snapshot_graph.py --restore data/snapshots/<file>.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("snapshot")

sys.path.insert(0, ".")

from app.context_graph_client import connect_neo4j, close_neo4j, execute_cypher  # noqa: E402

# Natural key per label — what MERGE matches on, so a restore is idempotent.
KEY_PROPERTY = {"Video": "id", "Segment": "id", "Entity": "key", "Topic": "key"}
LABELS = list(KEY_PROPERTY)
SNAPSHOT_DIR = Path(__file__).resolve().parents[2] / "data" / "snapshots"


async def export_graph() -> dict:
    nodes: dict[str, list[dict]] = {}
    for label in LABELS:
        rows = await execute_cypher(
            f"MATCH (n:{label}) RETURN properties(n) AS props",
            collect=False,
        )
        nodes[label] = [r["props"] for r in rows]
        log.info("  %-8s %d", label, len(nodes[label]))

    rels = await execute_cypher(
        """
        MATCH (a)-[r]->(b)
        WHERE labels(a)[0] IN $labels AND labels(b)[0] IN $labels
        RETURN labels(a)[0] AS a_label, labels(b)[0] AS b_label, type(r) AS type,
               a[$keys[labels(a)[0]]] AS a_key, b[$keys[labels(b)[0]]] AS b_key
        """,
        {"labels": LABELS, "keys": KEY_PROPERTY},
        collect=False,
    )
    log.info("  %-8s %d", "rels", len(rels))
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "key_property": KEY_PROPERTY,
        "nodes": nodes,
        "relationships": rels,
    }


async def import_graph(snapshot: dict) -> None:
    key_property = snapshot.get("key_property", KEY_PROPERTY)
    for label, rows in snapshot.get("nodes", {}).items():
        if not rows:
            continue
        key = key_property.get(label, "id")
        await execute_cypher(
            f"""
            UNWIND $rows AS props
            MERGE (n:{label} {{{key}: props.{key}}})
            SET n += props
            """,
            {"rows": rows},
            collect=False,
        )
        log.info("  %-8s %d restored", label, len(rows))

    by_type: dict[tuple[str, str, str], list[dict]] = {}
    for r in snapshot.get("relationships", []):
        by_type.setdefault((r["a_label"], r["type"], r["b_label"]), []).append(r)
    for (a_label, rel_type, b_label), rows in by_type.items():
        a_key = key_property.get(a_label, "id")
        b_key = key_property.get(b_label, "id")
        await execute_cypher(
            f"""
            UNWIND $rows AS row
            MATCH (a:{a_label} {{{a_key}: row.a_key}})
            MATCH (b:{b_label} {{{b_key}: row.b_key}})
            MERGE (a)-[:{rel_type}]->(b)
            """,
            {"rows": rows},
            collect=False,
        )
        log.info("  (%s)-[:%s]->(%s) %d restored", a_label, rel_type, b_label, len(rows))


CONSTRAINTS = [
    "CREATE CONSTRAINT video_id_unique IF NOT EXISTS FOR (n:Video) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT segment_id_unique IF NOT EXISTS FOR (n:Segment) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT entity_key_unique IF NOT EXISTS FOR (n:Entity) REQUIRE n.key IS UNIQUE",
    "CREATE CONSTRAINT topic_key_unique IF NOT EXISTS FOR (n:Topic) REQUIRE n.key IS UNIQUE",
]


def _literal(value) -> str:
    """Render a Python value as a Cypher literal.

    JSON string escaping is a subset of Cypher's, so json.dumps is safe for the
    scalars; maps have to be built by hand because Cypher map keys are bare
    identifiers rather than quoted strings.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ", ".join(_literal(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"`{k}`: {_literal(v)}" for k, v in value.items()) + "}"
    return json.dumps(str(value))


def to_cypher(snapshot: dict, with_embeddings: bool = False) -> str:
    key_property = snapshot.get("key_property", KEY_PROPERTY)
    nodes = snapshot.get("nodes", {})
    rels = snapshot.get("relationships", [])

    counts = ", ".join(f"{len(v)} {k}" for k, v in nodes.items() if v)
    out = [
        "// Video Context Graph export",
        f"// created {snapshot.get('created_at', '?')}",
        f"// {counts}, {len(rels)} relationships",
        "//",
        "// Paste into Neo4j Browser, or run:",
        "//   cypher-shell -u neo4j -p password -f <this file>",
        "//",
        "// Safe to re-run: every node is MERGE'd on its natural key, so this adds to",
        "// an existing graph rather than replacing it.",
        "",
    ]
    if not with_embeddings:
        out += ["// Segment embeddings omitted — re-export with --with-embeddings for",
                "// semantic search.", ""]
    out += [c + ";" for c in CONSTRAINTS] + [""]

    for label, rows in nodes.items():
        if not rows:
            continue
        key = key_property.get(label, "id")
        cleaned = [
            {k: v for k, v in row.items() if with_embeddings or k != "embedding"}
            for row in rows
        ]
        out.append(f"// --- {label} ({len(cleaned)}) " + "-" * (52 - len(label)))
        out.append("UNWIND [")
        out.append(",\n".join("  " + _literal(r) for r in cleaned))
        out.append("] AS row")
        out.append(f"MERGE (n:{label} {{{key}: row.{key}}})")
        out.append("SET n += row;")
        out.append("")

    by_type: dict[tuple[str, str, str], list[dict]] = {}
    for r in rels:
        by_type.setdefault((r["a_label"], r["type"], r["b_label"]), []).append(r)
    for (a_label, rel_type, b_label), rows in by_type.items():
        a_key = key_property.get(a_label, "id")
        b_key = key_property.get(b_label, "id")
        out.append(f"// --- ({a_label})-[:{rel_type}]->({b_label}) ({len(rows)}) ---")
        out.append("UNWIND [")
        out.append(",\n".join(
            "  {a: %s, b: %s}" % (_literal(r["a_key"]), _literal(r["b_key"])) for r in rows
        ))
        out.append("] AS row")
        out.append(f"MATCH (a:{a_label} {{{a_key}: row.a}})")
        out.append(f"MATCH (b:{b_label} {{{b_key}: row.b}})")
        out.append(f"MERGE (a)-[:{rel_type}]->(b);")
        out.append("")

    out += [
        "// Everything, once loaded:",
        "//   MATCH p=(v:Video)-[:HAS_SEGMENT]->(:Segment)-[:MENTIONS|ABOUT]->() RETURN p",
        "// Entities shared by more than one video:",
        "//   MATCH (v:Video)-[:HAS_SEGMENT]->(:Segment)-[:MENTIONS]->(e:Entity)",
        "//   WITH e, count(DISTINCT v) AS n WHERE n > 1 RETURN e.name, e.type, n ORDER BY n DESC",
        "",
    ]
    return "\n".join(out)


def list_snapshots() -> None:
    files = sorted(SNAPSHOT_DIR.glob("*.json")) if SNAPSHOT_DIR.is_dir() else []
    if not files:
        print(f"No snapshots in {SNAPSHOT_DIR}")
        return
    for f in files:
        try:
            meta = json.loads(f.read_text(encoding="utf-8"))
            counts = ", ".join(f"{k} {len(v)}" for k, v in meta.get("nodes", {}).items())
        except Exception:
            counts = "unreadable"
        print(f"{f.name:<44} {f.stat().st_size / 1e6:6.1f} MB  {counts}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--save", nargs="?", const="", metavar="PATH",
                       help="write a snapshot (default: data/snapshots/graph-<utc>.json)")
    group.add_argument("--cypher", nargs="?", const="", metavar="PATH",
                       help="write a shareable .cypher script instead of JSON")
    group.add_argument("--restore", metavar="PATH", help="merge a snapshot back into the graph")
    group.add_argument("--list", action="store_true", help="list saved snapshots")
    parser.add_argument("--with-embeddings", action="store_true",
                        help="include segment embeddings in a --cypher export (much larger)")
    args = parser.parse_args()

    if args.list:
        list_snapshots()
        return

    await connect_neo4j()
    try:
        if args.restore:
            path = Path(args.restore)
            if not path.is_absolute() and not path.exists():
                path = SNAPSHOT_DIR / path.name
            log.info("Restoring %s ...", path)
            await import_graph(json.loads(path.read_text(encoding="utf-8")))
            log.info("Restored. Existing data was merged, not replaced.")
            return

        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
        log.info("Exporting graph ...")
        data = await export_graph()

        if args.cypher is not None:
            path = Path(args.cypher) if args.cypher else SNAPSHOT_DIR / f"graph-{stamp}.cypher"
            path.write_text(to_cypher(data, with_embeddings=args.with_embeddings),
                            encoding="utf-8")
        else:
            path = Path(args.save) if args.save else SNAPSHOT_DIR / f"graph-{stamp}.json"
            path.write_text(json.dumps(data), encoding="utf-8")
        log.info("Wrote %s (%.2f MB)", path, path.stat().st_size / 1e6)
    finally:
        await close_neo4j()


if __name__ == "__main__":
    asyncio.run(main())
