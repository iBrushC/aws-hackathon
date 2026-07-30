# Whisker

Meet-logger front end for the context graph. Who you met, their face from the
recording, what they said, and a chat that can find them again.

Plain HTML / CSS / JS. No build step, no framework, no package.json.

## run

Needs the backend on :8000 and a graph with something in it — see the
[repo README](../README.md). Then any static server:

```bash
py -3 -m http.server 5173 --directory .
```

Open http://localhost:5173.

Port 5173 matters: the backend only accepts browser origins listed in
`CORS_ORIGINS`, and 5173 is what's in `.env.example`. Serving from another port
means adding it there too. Point the page at a different API with `?api=` or
`localStorage.setItem("whisker.api", "…")`.

With the backend down the page still renders — it falls back to the seeded demo
roster in `seedDemoSession()` so it's never blank.

## files

| file | what's in it |
| --- | --- |
| `index.html` | markup |
| `styles.css` | DM Sans + Lora, black/white with a pale-blue accent |
| `graph.js` | everything that talks to the graph: people, clips, frames, chat |
| `app.js` | state and rendering |

## where the data comes from

`graph.js` pulls `Entity {type: 'person'}` out of Neo4j along with the segments
they appear in. Affiliations are organisations named in the same segment — the
closest thing the graph has to "where do I know them from". Tags are the
segment's topics. The blurb is their longest segment summary, which in practice
is the one where they actually said something rather than a pan across the room.

Chat goes to the backend's graph agent, not string matching over the cards, so it
can answer things like "who did I meet who works on agents?". The `session_id` is
kept so follow-up questions still have context.

## the frames

TwelveLabs writes a JPEG every 5 seconds next to the HLS playlist. There's no
"frame at time t" endpoint, but the paths are predictable, so `frameUrl()` rounds
a timecode to the 5-second grid and builds the URL. Off-grid seconds 403, hence
the rounding. That's how a person's avatar ends up being their face at the moment
they first appear.

A `Video` node with no playback URL has no frames behind it, and those cards fall
back to generated placeholders. It happens when ingestion wrote the video before
TwelveLabs finished HLS packaging — `wait_for_playback_url()` in the backend
exists to stop that, but older rows may still need backfilling.
