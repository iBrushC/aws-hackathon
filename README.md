# Conference People Context Graph

Point it at a recording of a conference or hackathon and it builds a Neo4j graph
of who was there, what they said, and when — then lets you ask "who was that
person I met today?" and get a name, an affiliation, and a timecode back.

Built for [Hack the Video Agent Context Graph](https://luma.com/hack-video-agent-context-graph-jul30-2026).

Two front ends sit on the same graph:

- **`app/`** — Whisker, the meet-logger. People cards with their actual face from
  the recording, clips, and a chat that answers "who was the guy talking about
  note-taking glasses?". Plain HTML/CSS/JS, no build step.
- **`frontend/`** — the graph explorer. Next.js + NVL, for looking at the graph
  itself rather than the people in it.

The pipeline underneath both: TwelveLabs (Marengo + Pegasus) understands the
video, OpenAI turns its prose into schema-validated segments, Marengo embeds
them, Neo4j stores the lot. Entities and topics are `MERGE`'d on a normalised
name, so the same person across two recordings collapses to one node — that
shared node is the whole point.

## what you need

- **uv** (Python 3.10–3.13), **Node 18+**, **Docker**
- A **TwelveLabs** key (`tlk_…`) and an **OpenAI** key (`sk-…`). Free tier is
  enough for TwelveLabs; OpenAI needs prepaid credit.
- `make` is *not* required and the commands below don't use it.

Copy `.env.example` to `.env` and fill in the two keys. The Neo4j values already
match the bundled `docker-compose.yml`, so leave them alone unless you're on Aura.

## run it

Neo4j first — it holds everything and is the only stateful piece:

```bash
docker compose up -d
```

Install both halves:

```bash
uv sync --project backend --extra dev
```

```bash
npm install --prefix frontend
```

Check your keys before spending minutes on a video. This catches a wrong key or
a model your account can't reach in about ten seconds:

```bash
uv run --directory backend python scripts/smoke_keys.py
```

Ingest a video. Local file or a directly-fetchable MP4 URL — YouTube links don't
work, TwelveLabs has to `GET` the raw file:

```bash
uv run --directory backend python scripts/ingest.py "C:\path\to\clip.mp4"
```

Run it with no arguments and it takes everything in `data/videos/`. Ingesting is
additive: the graph grows with each video and shared people link them together.
Nothing is wiped unless you ask.

Then the API and whichever front end you want:

```bash
uv run --directory backend uvicorn app.main:app --port 8000 --loop asyncio
```

```bash
py -3 -m http.server 5173 --directory app
```

```bash
npm --prefix frontend run dev
```

Whisker on http://localhost:5173, the graph explorer on http://localhost:3000,
Neo4j Browser on http://localhost:7474 (`neo4j` / `password`).

`--loop asyncio` is not optional on Windows — uvloop isn't available there.

## what ingestion actually does

1. Upload to TwelveLabs. Files over 200 MB go up in parts with per-part retries,
   so a dropped connection costs a part instead of the whole transfer.
2. Index with Marengo + Pegasus.
3. Analyze with Pegasus. A single analyze call is capped at 4096 output tokens,
   which silently truncates anything past a few minutes, so videos longer than
   five minutes are walked one window at a time and stitched back together.
4. Structure the prose with OpenAI into segments with canonicalized entities.
5. Embed each segment with Marengo (512-dim) and write to Neo4j.

An 18-minute clip takes about eight minutes end to end, most of it indexing.

## the graph

```
(:Video)-[:HAS_SEGMENT]->(:Segment {embedding})   // vector index on the embedding
(:Segment)-[:NEXT]->(:Segment)                     // temporal order
(:Segment)-[:MENTIONS]->(:Entity)                  // MERGE'd across videos
(:Segment)-[:ABOUT]->(:Topic)                      // MERGE'd across videos
```

`Entity.type` is one of person, organization, location, object, product, brand,
event, concept. Whisker reads the `person` ones.

## keeping and sharing the graph

The graph lives in the `neo4j_data` Docker volume and survives container
restarts. It does not survive `docker compose down -v` or a `reset_database()`,
and re-ingesting costs API minutes, so snapshot it:

```bash
uv run --directory backend python scripts/snapshot_graph.py --save
```

To hand the graph to someone else, export it as a Cypher script they can paste
straight into their own Neo4j — self-contained, no scripts or credentials needed
on their end:

```bash
uv run --directory backend python scripts/snapshot_graph.py --cypher
```

Both land in `data/snapshots/` (gitignored — exports carry playback URLs and
transcripts of real people). Restoring is additive, so an old snapshot can go on
top of a live graph without clobbering it.

## scripts worth knowing

| command | what it does |
| --- | --- |
| `scripts/ingest.py <video…>` | the pipeline. no args = everything in `data/videos/` |
| `scripts/ingest.py --schema-only` | constraints and indexes, no data |
| `scripts/smoke_keys.py` | are the keys and models actually usable |
| `scripts/smoke_graph.py` | exercises the Neo4j write path with fake data, no API keys |
| `scripts/snapshot_graph.py` | `--save` / `--restore` / `--cypher` / `--list` |

Wipe the graph with:

```bash
uv run --directory backend python -c "import asyncio; from app.context_graph_client import reset_database; asyncio.run(reset_database())"
```

## known rough edges

- Entity names come from an LLM, so they vary between runs. The same person can
  come back as "Presenter" one run and by name the next. The `MERGE` mechanism
  holds; the specific names don't.
- Re-ingesting a video deletes its old segments but leaves its old Entity and
  Topic nodes behind as orphans. Nothing cleans them up yet.
- Ingesting the same file twice mints a new TwelveLabs id, so it lands as a
  second `Video` node rather than replacing the first.

[HOWTO.md](HOWTO.md) walks through the cross-video merge with two clips.
