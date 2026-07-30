/* Reads the people Whisker knows about out of the Neo4j context graph.
 *
 * The graph is built by the ingestion pipeline (backend/scripts/ingest.py):
 * each video becomes time-coded Segments, and every person seen or named in a
 * segment becomes an Entity with type "person", MERGE'd by normalised name so
 * the same person across several recordings is one node. That is exactly the
 * "who was that again?" lookup this page needs, so the mock roster in app.js is
 * replaced by whatever the graph actually holds.
 *
 * No build step: this is a plain script tag talking to the backend's /api.
 */

const GRAPH_API =
  new URLSearchParams(location.search).get("api") ||
  localStorage.getItem("whisker.api") ||
  "http://localhost:8000/api";

// One row per person, with the moments they appear in and who/what was around
// them. Affiliations come from organisations named in the same segment — the
// closest thing the graph has to "where do I know them from".
const PEOPLE_CYPHER = `
MATCH (p:Entity {type: 'person'})<-[:MENTIONS]-(s:Segment)<-[:HAS_SEGMENT]-(v:Video)
OPTIONAL MATCH (s)-[:MENTIONS]->(o:Entity)
  WHERE o.type IN ['organization', 'product', 'brand'] AND o.key <> p.key
OPTIONAL MATCH (s)-[:ABOUT]->(t:Topic)
WITH p, s, v, collect(DISTINCT o.name) AS orgs, collect(DISTINCT t.name) AS topics
RETURN p.name AS name,
       p.key AS key,
       count(DISTINCT s) AS moments,
       min(s.start_sec) AS firstSec,
       collect(DISTINCT s.summary) AS summaries,
       collect(orgs) AS orgGroups,
       collect(topics) AS topicGroups,
       collect(DISTINCT {
         video: v.title, url: v.url,
         start: s.start_sec, end: s.end_sec, summary: s.summary
       }) AS moments_detail
ORDER BY moments DESC, name
`;

async function runCypher(query, parameters) {
  const res = await fetch(`${GRAPH_API}/cypher`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, parameters: parameters || {} }),
    signal: AbortSignal.timeout(15000),
  });
  if (!res.ok) throw new Error(`cypher ${res.status}: ${await res.text()}`);
  const data = await res.json();
  return data.results || [];
}

function flattenUnique(groups) {
  const out = [];
  for (const group of groups || []) {
    for (const value of group || []) {
      if (value && !out.includes(value)) out.push(value);
    }
  }
  return out;
}

function initialsOf(name) {
  return name
    .split(/\s+/)
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

/* A person's "summary" is the segment that shows them best — the longest one,
 * which in practice is the one where they actually say something rather than
 * the pans across the room. */
function bestSummary(summaries) {
  return (summaries || [])
    .filter(Boolean)
    .sort((a, b) => b.length - a.length)[0] || "";
}

function toPerson(row) {
  const affiliations = flattenUnique(row.orgGroups);
  const topics = flattenUnique(row.topicGroups);
  const moments = (row.moments_detail || []).filter((m) => typeof m.start === "number");
  // Their earliest appearance in a copy of the recording we can actually pull
  // frames from.
  const firstPlayable = [...moments]
    .filter((m) => m.url)
    .sort((a, b) => a.start - b.start)[0];
  return {
    id: row.key,
    name: row.name,
    role: affiliations.slice(0, 2).join(" · ") || `Seen in ${row.moments} moment${row.moments === 1 ? "" : "s"}`,
    tags: topics.slice(0, 3).map((t) => t.toLowerCase()),
    summary: bestSummary(row.summaries),
    moments: row.moments,
    firstSec: row.firstSec,
    affiliations,
    topics,
    clips: moments,
    initials: initialsOf(row.name),
    // Their face, from the recording, at the moment they first show up — the
    // whole point of "who was that again?".
    frame: firstPlayable ? frameUrl(firstPlayable.url, firstPlayable.start) : null,
  };
}

function toClips(people) {
  const seen = new Set();
  const clips = [];
  for (const person of people) {
    // Re-ingesting a video mints a fresh id, so the same recording can appear
    // twice with only one copy carrying a playback URL. Take the playable one.
    const moments = [...person.clips].sort((a, b) => (b.url ? 1 : 0) - (a.url ? 1 : 0));
    for (const moment of moments) {
      const id = `${moment.video}#${moment.start}`;
      if (seen.has(id)) continue;
      seen.add(id);
      clips.push({
        id,
        title: `${person.name} — ${moment.video}`,
        sub: `${formatClock(moment.start)}–${formatClock(moment.end)}`,
        tag: person.affiliations[0] || "Moment",
        durationSec: Math.max(1, Math.round((moment.end || 0) - (moment.start || 0))),
        // TwelveLabs hands back an HLS playlist, which no browser but Safari
        // plays from a bare <video src>. Keep the URL for the detail view and
        // let the card fall back to its generated poster.
        src: null,
        hlsUrl: moment.url || null,
        frame: frameUrl(moment.url, moment.start),
        startSec: moment.start,
        summary: moment.summary,
        person: person.name,
      });
    }
  }
  return clips.sort((a, b) => a.startSec - b.startSec);
}

function formatClock(sec) {
  const s = Math.max(0, Math.round(sec || 0));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

// TwelveLabs writes a JPEG every 5 seconds alongside the HLS playlist. There is
// no "frame at time t" endpoint, but the paths are predictable, so a moment can
// show what was actually on screen instead of a coloured placeholder. Seconds
// off the 5s grid return 403, hence the rounding.
const THUMBNAIL_INTERVAL_SEC = 5;

function frameUrl(hlsUrl, sec) {
  if (!hlsUrl) return null;
  const base = hlsUrl.replace(/\/hlses\/[^/]+$/, "/thumbnails");
  if (base === hlsUrl) return null;
  const grid = THUMBNAIL_INTERVAL_SEC;
  const t = Math.max(0, Math.round((sec || 0) / grid) * grid);
  return `${base}/${t}.jpeg`;
}

/* Ask the graph-backed agent instead of substring-matching the roster: it can
 * follow relationships ("who did I meet who works on agents?") that a text
 * match over the cards cannot. */
async function askAgent(message, sessionId) {
  const res = await fetch(`${GRAPH_API}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId || null }),
    signal: AbortSignal.timeout(120000),
  });
  if (!res.ok) throw new Error(`chat ${res.status}`);
  return res.json();
}

async function loadGraphSession() {
  const rows = await runCypher(PEOPLE_CYPHER);
  const people = rows.map(toPerson);
  return { people, clips: toClips(people) };
}

window.WhiskerGraph = { GRAPH_API, loadGraphSession, askAgent, runCypher, formatClock };
