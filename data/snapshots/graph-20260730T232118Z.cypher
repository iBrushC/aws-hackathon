// Video Context Graph export
// created 2026-07-30T23:21:18.675716+00:00
// 1 Video, 5 Segment, 6 Entity, 6 Topic, 36 relationships
//
// Paste into Neo4j Browser, or run:
//   cypher-shell -u neo4j -p password -f <this file>
//
// Safe to re-run: every node is MERGE'd on its natural key, so this adds to
// an existing graph rather than replacing it.

// Segment embeddings omitted — re-export with --with-embeddings for
// semantic search.

CREATE CONSTRAINT video_id_unique IF NOT EXISTS FOR (n:Video) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT segment_id_unique IF NOT EXISTS FOR (n:Segment) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT entity_key_unique IF NOT EXISTS FOR (n:Entity) REQUIRE n.key IS UNIQUE;
CREATE CONSTRAINT topic_key_unique IF NOT EXISTS FOR (n:Topic) REQUIRE n.key IS UNIQUE;

// --- Video (1) -----------------------------------------------
UNWIND [
  {`summary`: "In a busy indoor event space, children interact with and photograph a small robot on a table. A boy holding a tablet appears to control it, then shouts \"Go, go, go!\" as the robot rapidly moves forward.", `id`: "6a6bdb35b9dc44a905219f05", `title`: "incheong-rescueing", `duration_sec`: 26.733333587646484, `tl_index_id`: "6a6bab0e39bf4592836c2eef", `domain`: "video-context-graph", `url`: "https://deuqpmn4rs7j5.cloudfront.net/6a6b8ea1308815828b42f1bd/assets/6a6bdb35b9dc44a905219f05/hlses/playlist.m3u8"}
] AS row
MERGE (n:Video {id: row.id})
SET n += row;

// --- Segment (5) ---------------------------------------------
UNWIND [
  {`summary`: "A boy in a light blue T-shirt stands beside a table holding a tablet near a small robot, in a large room with people and tables.", `id`: "6a6bdb35b9dc44a905219f05#0", `transcript`: "", `idx`: 0, `start_sec`: 0.0, `domain`: "video-context-graph", `video_id`: "6a6bdb35b9dc44a905219f05", `on_screen_text`: "", `end_sec`: 3.0},
  {`summary`: "The camera pans right to show a girl in a green shirt photographing the small robot while the boy remains in the background. More attendees and tables are visible around the room.", `id`: "6a6bdb35b9dc44a905219f05#1", `transcript`: "", `idx`: 1, `start_sec`: 3.0, `domain`: "video-context-graph", `video_id`: "6a6bdb35b9dc44a905219f05", `on_screen_text`: "", `end_sec`: 18.0},
  {`summary`: "The boy in the light blue T-shirt walks away from the table as the camera follows him. The girl continues photographing the robot.", `id`: "6a6bdb35b9dc44a905219f05#2", `transcript`: "", `idx`: 2, `start_sec`: 18.0, `domain`: "video-context-graph", `video_id`: "6a6bdb35b9dc44a905219f05", `on_screen_text`: "", `end_sec`: 21.0},
  {`summary`: "The camera pans back to the girl in the green shirt and the small robot on the table. A man in a blue shirt stands beside her amid the event attendees and tables.", `id`: "6a6bdb35b9dc44a905219f05#3", `transcript`: "", `idx`: 3, `start_sec`: 21.0, `domain`: "video-context-graph", `video_id`: "6a6bdb35b9dc44a905219f05", `on_screen_text`: "", `end_sec`: 26.0},
  {`summary`: "The boy turns toward the small robot, gestures, and shouts a command. The robot rapidly moves forward.", `id`: "6a6bdb35b9dc44a905219f05#4", `transcript`: "Go, go, go!", `idx`: 4, `start_sec`: 26.0, `domain`: "video-context-graph", `video_id`: "6a6bdb35b9dc44a905219f05", `on_screen_text`: "", `end_sec`: 27.0}
] AS row
MERGE (n:Segment {id: row.id})
SET n += row;

// --- Entity (6) ----------------------------------------------
UNWIND [
  {`name`: "Boy In Light Blue T-Shirt", `domain`: "video-context-graph", `type`: "person", `key`: "boy in light blue t-shirt"},
  {`name`: "Tablet", `domain`: "video-context-graph", `type`: "object", `key`: "tablet"},
  {`name`: "Small Robot", `domain`: "video-context-graph", `type`: "object", `key`: "small robot"},
  {`name`: "Indoor Event Space", `domain`: "video-context-graph", `type`: "location", `key`: "indoor event space"},
  {`name`: "Girl In Green Shirt", `domain`: "video-context-graph", `type`: "person", `key`: "girl in green shirt"},
  {`name`: "Man In Blue Shirt", `domain`: "video-context-graph", `type`: "person", `key`: "man in blue shirt"}
] AS row
MERGE (n:Entity {key: row.key})
SET n += row;

// --- Topic (6) -----------------------------------------------
UNWIND [
  {`name`: "Robot Demonstration", `domain`: "video-context-graph", `key`: "robot demonstration"},
  {`name`: "Robot Control", `domain`: "video-context-graph", `key`: "robot control"},
  {`name`: "Photography", `domain`: "video-context-graph", `key`: "photography"},
  {`name`: "Movement", `domain`: "video-context-graph", `key`: "movement"},
  {`name`: "Robot Activation", `domain`: "video-context-graph", `key`: "robot activation"},
  {`name`: "Robot Movement", `domain`: "video-context-graph", `key`: "robot movement"}
] AS row
MERGE (n:Topic {key: row.key})
SET n += row;

// --- (Video)-[:HAS_SEGMENT]->(Segment) (5) ---
UNWIND [
  {a: "6a6bdb35b9dc44a905219f05", b: "6a6bdb35b9dc44a905219f05#4"},
  {a: "6a6bdb35b9dc44a905219f05", b: "6a6bdb35b9dc44a905219f05#3"},
  {a: "6a6bdb35b9dc44a905219f05", b: "6a6bdb35b9dc44a905219f05#2"},
  {a: "6a6bdb35b9dc44a905219f05", b: "6a6bdb35b9dc44a905219f05#1"},
  {a: "6a6bdb35b9dc44a905219f05", b: "6a6bdb35b9dc44a905219f05#0"}
] AS row
MATCH (a:Video {id: row.a})
MATCH (b:Segment {id: row.b})
MERGE (a)-[:HAS_SEGMENT]->(b);

// --- (Segment)-[:NEXT]->(Segment) (4) ---
UNWIND [
  {a: "6a6bdb35b9dc44a905219f05#0", b: "6a6bdb35b9dc44a905219f05#1"},
  {a: "6a6bdb35b9dc44a905219f05#1", b: "6a6bdb35b9dc44a905219f05#2"},
  {a: "6a6bdb35b9dc44a905219f05#2", b: "6a6bdb35b9dc44a905219f05#3"},
  {a: "6a6bdb35b9dc44a905219f05#3", b: "6a6bdb35b9dc44a905219f05#4"}
] AS row
MATCH (a:Segment {id: row.a})
MATCH (b:Segment {id: row.b})
MERGE (a)-[:NEXT]->(b);

// --- (Segment)-[:ABOUT]->(Topic) (10) ---
UNWIND [
  {a: "6a6bdb35b9dc44a905219f05#0", b: "robot control"},
  {a: "6a6bdb35b9dc44a905219f05#0", b: "robot demonstration"},
  {a: "6a6bdb35b9dc44a905219f05#1", b: "robot demonstration"},
  {a: "6a6bdb35b9dc44a905219f05#1", b: "photography"},
  {a: "6a6bdb35b9dc44a905219f05#2", b: "photography"},
  {a: "6a6bdb35b9dc44a905219f05#2", b: "movement"},
  {a: "6a6bdb35b9dc44a905219f05#3", b: "robot demonstration"},
  {a: "6a6bdb35b9dc44a905219f05#3", b: "photography"},
  {a: "6a6bdb35b9dc44a905219f05#4", b: "robot movement"},
  {a: "6a6bdb35b9dc44a905219f05#4", b: "robot activation"}
] AS row
MATCH (a:Segment {id: row.a})
MATCH (b:Topic {key: row.b})
MERGE (a)-[:ABOUT]->(b);

// --- (Segment)-[:MENTIONS]->(Entity) (17) ---
UNWIND [
  {a: "6a6bdb35b9dc44a905219f05#0", b: "indoor event space"},
  {a: "6a6bdb35b9dc44a905219f05#0", b: "small robot"},
  {a: "6a6bdb35b9dc44a905219f05#0", b: "tablet"},
  {a: "6a6bdb35b9dc44a905219f05#0", b: "boy in light blue t-shirt"},
  {a: "6a6bdb35b9dc44a905219f05#1", b: "indoor event space"},
  {a: "6a6bdb35b9dc44a905219f05#1", b: "small robot"},
  {a: "6a6bdb35b9dc44a905219f05#1", b: "boy in light blue t-shirt"},
  {a: "6a6bdb35b9dc44a905219f05#1", b: "girl in green shirt"},
  {a: "6a6bdb35b9dc44a905219f05#2", b: "small robot"},
  {a: "6a6bdb35b9dc44a905219f05#2", b: "girl in green shirt"},
  {a: "6a6bdb35b9dc44a905219f05#2", b: "boy in light blue t-shirt"},
  {a: "6a6bdb35b9dc44a905219f05#3", b: "indoor event space"},
  {a: "6a6bdb35b9dc44a905219f05#3", b: "small robot"},
  {a: "6a6bdb35b9dc44a905219f05#3", b: "man in blue shirt"},
  {a: "6a6bdb35b9dc44a905219f05#3", b: "girl in green shirt"},
  {a: "6a6bdb35b9dc44a905219f05#4", b: "small robot"},
  {a: "6a6bdb35b9dc44a905219f05#4", b: "boy in light blue t-shirt"}
] AS row
MATCH (a:Segment {id: row.a})
MATCH (b:Entity {key: row.b})
MERGE (a)-[:MENTIONS]->(b);

// Everything, once loaded:
//   MATCH p=(v:Video)-[:HAS_SEGMENT]->(:Segment)-[:MENTIONS|ABOUT]->() RETURN p
// Entities shared by more than one video:
//   MATCH (v:Video)-[:HAS_SEGMENT]->(:Segment)-[:MENTIONS]->(e:Entity)
//   WITH e, count(DISTINCT v) AS n WHERE n > 1 RETURN e.name, e.type, n ORDER BY n DESC
