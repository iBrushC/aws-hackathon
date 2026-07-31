# end-to-end test prompt

Hand this to Codex (or any agent) verbatim. It assumes no knowledge of how the
repo got built.

---

Run an end-to-end test of the Conference People Context Graph and report what
passed and what didn't. Don't fix anything unless I ask — I want the state of it.

## what this is

`C:\Users\magic\Documents\hackathon\aws-hackathon`, branch `main-real`. It turns
conference video into a Neo4j knowledge graph and serves two front ends off it:

- `app/` — Whisker, a static HTML page. People cards, clips, chat.
- `frontend/` — a Next.js graph explorer.
- `backend/` — the ingest pipeline and a FastAPI + Strands agent on :8000.

## before you start

This spends real TwelveLabs minutes and OpenAI tokens on every ingest, so run the
pipeline once, not in a loop.

Shell is PowerShell on Windows. `make` is not installed — never use it. Every
Makefile target has to be run as its underlying command. `uvicorn` needs
`--loop asyncio`; uvloop doesn't exist on Windows and it will not start without it.

Docker Desktop must be running. `.env` must already exist at the repo root with a
TwelveLabs and an OpenAI key — do not create one, do not print its contents, and
do not commit it.

Pick a test video. `data/videos/bbb_1080p_30fps_normal_85sec.mp4` ships with the
repo and works, but it's a cartoon with no people, so the Whisker people checks
(step 5) will come up empty with it — that's the clip's fault, not a bug. If a
recording of actual people is available, use that instead and say which you used.

## step 0 — protect what's there

The graph is not disposable; re-ingesting costs money. Snapshot before wiping:

```bash
uv run --directory backend python scripts/snapshot_graph.py --save
```

Note the filename it writes into `data/snapshots/`. You'll restore it in step 8.

## step 1 — clean slate

```bash
docker compose up -d
```

```bash
uv run --directory backend python -c "import asyncio; from app.context_graph_client import reset_database; asyncio.run(reset_database())"
```

**Pass:** `MATCH (n) RETURN count(n)` returns 0. Run it with:

```bash
docker exec aws-hackathon-neo4j-1 cypher-shell -u neo4j -p password "MATCH (n) RETURN count(n) AS nodes;"
```

## step 2 — credentials

```bash
uv run --directory backend python scripts/smoke_keys.py
```

**Pass:** `ALL CREDENTIAL CHECKS PASSED`. If a model check fails, stop and report
it — ingestion will still work but the chat won't, and that's worth knowing
before you spend the minutes.

## step 3 — the graph write path, without spending anything

```bash
uv run --directory backend python scripts/smoke_graph.py
```

**Pass:** `ALL CHECKS PASSED`. This writes synthetic nodes to prove the Neo4j
side works, then leaves them behind; step 4 does not clean them up, so subtract
2 videos / 3 segments from later counts, or wipe again first.

## step 4 — ingest

```bash
uv run --directory backend python scripts/ingest.py "<your video path>"
```

**Pass, all four:**
- ends with `Wrote video '<name>' (N segments) to Neo4j` and `Vector index ready`
- the `Structured into N segments covering Xs of Ys` line has X within a second
  or two of Y. Coverage well below the duration means the analysis got truncated.
- no `windows produced nothing` error
- no `No playback URL` warning

Report how long it took and the segment count.

## step 5 — services

Three, each in its own background process:

```bash
uv run --directory backend uvicorn app.main:app --port 8000 --loop asyncio
```

```bash
py -3 -m http.server 5173 --directory app
```

```bash
npm --prefix frontend run dev
```

If `frontend/node_modules` or `backend/.venv` are missing, install first with
`npm install --prefix frontend` and `uv sync --project backend --extra dev`.

**Pass:** `http://localhost:8000/health` returns `"status":"ok"` and
`"neo4j":true`; :5173 and :3000 both return 200.

## step 6 — the checks that actually matter

**API returns the video with a playback URL.** `GET /api/videos` — the video
should have a non-empty `url`. An empty one means ingestion wrote the row before
TwelveLabs finished HLS packaging, and there will be no video frames anywhere in
the UI.

**Embeddings do not reach the agent.** POST to `/api/cypher` with
`MATCH (v:Video)-[:HAS_SEGMENT]->(s:Segment) RETURN v,s` and check the response
body does **not** contain the string `embedding`. A 512-float array per segment
in there is what used to blow the OpenAI rate limit on any real graph. This is
the regression test for that.

**Whisker shows real people and real frames.** Open :5173. The people panel
should list `Entity {type:'person'}` nodes from the graph, and each avatar and
clip thumbnail should be a `cloudfront.net/...thumbnails/N.jpeg` URL that
actually loaded (`naturalWidth > 0`), not a generated `data:image/svg+xml`
placeholder.

> Known, not a bug: TwelveLabs generates those thumbnails about two minutes
> **after** ingestion reports done. If you open the page immediately everything
> 403s and falls back to placeholders permanently until reload. If frames are
> missing, wait two minutes, reload, and check again before calling it a failure.

**Chat answers from the graph.** Ask Whisker something only the video could
answer — name a specific object or moment in it. A good answer names a person or
thing and cites a timecode. Report the question and the answer verbatim.

**Graph explorer opens on data, not schema.** Open :3000, go to the Graph panel.
The subtitle should read `Video entity relationships`. If it says `Schema view`
with four generic bubbles, the initial load failed and fell back.

## step 7 — the shareable export

```bash
uv run --directory backend python scripts/snapshot_graph.py --cypher
```

Then replay the file it wrote back into the live database — it's all `MERGE`, so
a valid export changes nothing:

```bash
docker cp "<the .cypher file>" aws-hackathon-neo4j-1:/tmp/e2e.cypher
```

```bash
docker exec aws-hackathon-neo4j-1 cypher-shell -u neo4j -p password -f /tmp/e2e.cypher
```

**Pass:** exit code 0 and identical node counts before and after.

Pipe the file into `cypher-shell` from PowerShell instead and you'll get a BOM
parse error — that's PowerShell's pipe, not the file. Use `-f`.

## step 8 — put the graph back

```bash
uv run --directory backend python scripts/snapshot_graph.py --restore <step 0 filename>
```

Restoring merges rather than replaces, so the test video stays alongside what was
there before. Say what the final node counts are.

## report

One table: step, pass/fail, and the number or string you saw. For anything that
failed, give the command, the actual output, and your read on whether it's the
test, the environment, or the code. Confirm `git status` is still clean — the
test should not have modified a tracked file.
