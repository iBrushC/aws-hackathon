// Video Context Graph export
// created 2026-07-30T23:55:22.630988+00:00
// 1 Video, 10 Segment, 11 Entity, 12 Topic, 72 relationships
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
  {`summary`: "An animated gray, long-eared forest creature wakes in a tree-root den, explores a meadow, admires flowers and a butterfly, finds and eats an apple, and ends by watching the butterfly return.", `id`: "6a6be358b9dc44a90521d4c2", `title`: "bbb_1080p_30fps_normal_85sec", `duration_sec`: 85.06700134277344, `tl_index_id`: "6a6bab0e39bf4592836c2eef", `domain`: "video-context-graph", `url`: "https://deuqpmn4rs7j5.cloudfront.net/6a6b8ea1308815828b42f1bd/assets/6a6be358b9dc44a90521d4c2/hlses/playlist.m3u8"}
] AS row
MERGE (n:Video {id: row.id})
SET n += row;

// --- Segment (10) ---------------------------------------------
UNWIND [
  {`summary`: "A static view shows a large tree with moss at its base and a dark opening among the roots in a lush forest setting.", `id`: "6a6be358b9dc44a90521d4c2#0", `transcript`: "", `idx`: 0, `start_sec`: 0.0, `domain`: "video-context-graph", `video_id`: "6a6be358b9dc44a90521d4c2", `on_screen_text`: "", `end_sec`: 10.0},
  {`summary`: "The camera moves closer to the opening, revealing a large gray furry creature with long ears asleep inside the tree-root den.", `id`: "6a6be358b9dc44a90521d4c2#1", `transcript`: "", `idx`: 1, `start_sec`: 10.0, `domain`: "video-context-graph", `video_id`: "6a6be358b9dc44a90521d4c2", `on_screen_text`: "", `end_sec`: 22.0},
  {`summary`: "The creature wakes, stretches, yawns, and looks around with surprise as the camera reveals grass and scattered rocks nearby.", `id`: "6a6be358b9dc44a90521d4c2#2", `transcript`: "", `idx`: 2, `start_sec`: 22.0, `domain`: "video-context-graph", `video_id`: "6a6be358b9dc44a90521d4c2", `on_screen_text`: "", `end_sec`: 31.0},
  {`summary`: "From a low angle, the creature looks upward at the clear sky and smiles, with clouds and treetops visible.", `id`: "6a6be358b9dc44a90521d4c2#3", `transcript`: "", `idx`: 3, `start_sec`: 31.0, `domain`: "video-context-graph", `video_id`: "6a6be358b9dc44a90521d4c2", `on_screen_text`: "", `end_sec`: 38.0},
  {`summary`: "White flowers with yellow centers are shown as the creature enters and deeply sniffs them.", `id`: "6a6be358b9dc44a90521d4c2#4", `transcript`: "", `idx`: 4, `start_sec`: 38.0, `domain`: "video-context-graph", `video_id`: "6a6be358b9dc44a90521d4c2", `on_screen_text`: "", `end_sec`: 45.0},
  {`summary`: "The creature lies on its back in the grass and looks upward while a large pink butterfly with black wing markings flies overhead.", `id`: "6a6be358b9dc44a90521d4c2#5", `transcript`: "", `idx`: 5, `start_sec`: 45.0, `domain`: "video-context-graph", `video_id`: "6a6be358b9dc44a90521d4c2", `on_screen_text`: "", `end_sec`: 51.0},
  {`summary`: "In a wide meadow view, the butterfly lands on the creature's nose. The creature notices a fallen red apple, picks it up with its right hand, and speaks affectionately.", `id`: "6a6be358b9dc44a90521d4c2#6", `transcript`: "I love you. ... you.", `idx`: 6, `start_sec`: 51.0, `domain`: "video-context-graph", `video_id`: "6a6be358b9dc44a90521d4c2", `on_screen_text`: "", `end_sec`: 65.0},
  {`summary`: "The creature looks between the apple tree and the apple, takes a bite, and watches the butterfly fly away.", `id`: "6a6be358b9dc44a90521d4c2#7", `transcript`: "", `idx`: 7, `start_sec`: 65.0, `domain`: "video-context-graph", `video_id`: "6a6be358b9dc44a90521d4c2", `on_screen_text`: "", `end_sec`: 73.0},
  {`summary`: "From above, the creature sits on a branch of the apple tree and continues eating the apple.", `id`: "6a6be358b9dc44a90521d4c2#8", `transcript`: "", `idx`: 8, `start_sec`: 73.0, `domain`: "video-context-graph", `video_id`: "6a6be358b9dc44a90521d4c2", `on_screen_text`: "", `end_sec`: 80.0},
  {`summary`: "The creature stands in the grassy field, appears surprised as the butterfly returns, and gazes at it at the end.", `id`: "6a6be358b9dc44a90521d4c2#9", `transcript`: "you.", `idx`: 9, `start_sec`: 80.0, `domain`: "video-context-graph", `video_id`: "6a6be358b9dc44a90521d4c2", `on_screen_text`: "", `end_sec`: 85.0}
] AS row
MERGE (n:Segment {id: row.id})
SET n += row;

// --- Entity (11) ----------------------------------------------
UNWIND [
  {`name`: "Tree", `domain`: "video-context-graph", `type`: "object", `key`: "tree"},
  {`name`: "Forest", `domain`: "video-context-graph", `type`: "location", `key`: "forest"},
  {`name`: "Long-Eared Creature", `domain`: "video-context-graph", `type`: "object", `key`: "long-eared creature"},
  {`name`: "Grassland", `domain`: "video-context-graph", `type`: "location", `key`: "grassland"},
  {`name`: "Rock", `domain`: "video-context-graph", `type`: "object", `key`: "rock"},
  {`name`: "Sky", `domain`: "video-context-graph", `type`: "location", `key`: "sky"},
  {`name`: "Flower", `domain`: "video-context-graph", `type`: "object", `key`: "flower"},
  {`name`: "Butterfly", `domain`: "video-context-graph", `type`: "object", `key`: "butterfly"},
  {`name`: "Grass", `domain`: "video-context-graph", `type`: "object", `key`: "grass"},
  {`name`: "Apple", `domain`: "video-context-graph", `type`: "object", `key`: "apple"},
  {`name`: "Apple Tree", `domain`: "video-context-graph", `type`: "object", `key`: "apple tree"}
] AS row
MERGE (n:Entity {key: row.key})
SET n += row;

// --- Topic (12) -----------------------------------------------
UNWIND [
  {`name`: "Forest", `domain`: "video-context-graph", `key`: "forest"},
  {`name`: "Nature", `domain`: "video-context-graph", `key`: "nature"},
  {`name`: "Sleep", `domain`: "video-context-graph", `key`: "sleep"},
  {`name`: "Wildlife", `domain`: "video-context-graph", `key`: "wildlife"},
  {`name`: "Awakening", `domain`: "video-context-graph", `key`: "awakening"},
  {`name`: "Sky", `domain`: "video-context-graph", `key`: "sky"},
  {`name`: "Flower", `domain`: "video-context-graph", `key`: "flower"},
  {`name`: "Butterfly", `domain`: "video-context-graph", `key`: "butterfly"},
  {`name`: "Apple", `domain`: "video-context-graph", `key`: "apple"},
  {`name`: "Meadow", `domain`: "video-context-graph", `key`: "meadow"},
  {`name`: "Eating", `domain`: "video-context-graph", `key`: "eating"},
  {`name`: "Tree", `domain`: "video-context-graph", `key`: "tree"}
] AS row
MERGE (n:Topic {key: row.key})
SET n += row;

// --- (Video)-[:HAS_SEGMENT]->(Segment) (10) ---
UNWIND [
  {a: "6a6be358b9dc44a90521d4c2", b: "6a6be358b9dc44a90521d4c2#7"},
  {a: "6a6be358b9dc44a90521d4c2", b: "6a6be358b9dc44a90521d4c2#6"},
  {a: "6a6be358b9dc44a90521d4c2", b: "6a6be358b9dc44a90521d4c2#3"},
  {a: "6a6be358b9dc44a90521d4c2", b: "6a6be358b9dc44a90521d4c2#9"},
  {a: "6a6be358b9dc44a90521d4c2", b: "6a6be358b9dc44a90521d4c2#5"},
  {a: "6a6be358b9dc44a90521d4c2", b: "6a6be358b9dc44a90521d4c2#8"},
  {a: "6a6be358b9dc44a90521d4c2", b: "6a6be358b9dc44a90521d4c2#4"},
  {a: "6a6be358b9dc44a90521d4c2", b: "6a6be358b9dc44a90521d4c2#2"},
  {a: "6a6be358b9dc44a90521d4c2", b: "6a6be358b9dc44a90521d4c2#1"},
  {a: "6a6be358b9dc44a90521d4c2", b: "6a6be358b9dc44a90521d4c2#0"}
] AS row
MATCH (a:Video {id: row.a})
MATCH (b:Segment {id: row.b})
MERGE (a)-[:HAS_SEGMENT]->(b);

// --- (Segment)-[:NEXT]->(Segment) (9) ---
UNWIND [
  {a: "6a6be358b9dc44a90521d4c2#0", b: "6a6be358b9dc44a90521d4c2#1"},
  {a: "6a6be358b9dc44a90521d4c2#1", b: "6a6be358b9dc44a90521d4c2#2"},
  {a: "6a6be358b9dc44a90521d4c2#2", b: "6a6be358b9dc44a90521d4c2#3"},
  {a: "6a6be358b9dc44a90521d4c2#3", b: "6a6be358b9dc44a90521d4c2#4"},
  {a: "6a6be358b9dc44a90521d4c2#4", b: "6a6be358b9dc44a90521d4c2#5"},
  {a: "6a6be358b9dc44a90521d4c2#5", b: "6a6be358b9dc44a90521d4c2#6"},
  {a: "6a6be358b9dc44a90521d4c2#6", b: "6a6be358b9dc44a90521d4c2#7"},
  {a: "6a6be358b9dc44a90521d4c2#7", b: "6a6be358b9dc44a90521d4c2#8"},
  {a: "6a6be358b9dc44a90521d4c2#8", b: "6a6be358b9dc44a90521d4c2#9"}
] AS row
MATCH (a:Segment {id: row.a})
MATCH (b:Segment {id: row.b})
MERGE (a)-[:NEXT]->(b);

// --- (Segment)-[:ABOUT]->(Topic) (24) ---
UNWIND [
  {a: "6a6be358b9dc44a90521d4c2#0", b: "forest"},
  {a: "6a6be358b9dc44a90521d4c2#0", b: "nature"},
  {a: "6a6be358b9dc44a90521d4c2#1", b: "sleep"},
  {a: "6a6be358b9dc44a90521d4c2#1", b: "wildlife"},
  {a: "6a6be358b9dc44a90521d4c2#2", b: "awakening"},
  {a: "6a6be358b9dc44a90521d4c2#2", b: "nature"},
  {a: "6a6be358b9dc44a90521d4c2#3", b: "nature"},
  {a: "6a6be358b9dc44a90521d4c2#3", b: "sky"},
  {a: "6a6be358b9dc44a90521d4c2#4", b: "nature"},
  {a: "6a6be358b9dc44a90521d4c2#4", b: "flower"},
  {a: "6a6be358b9dc44a90521d4c2#5", b: "butterfly"},
  {a: "6a6be358b9dc44a90521d4c2#5", b: "nature"},
  {a: "6a6be358b9dc44a90521d4c2#6", b: "meadow"},
  {a: "6a6be358b9dc44a90521d4c2#6", b: "apple"},
  {a: "6a6be358b9dc44a90521d4c2#6", b: "butterfly"},
  {a: "6a6be358b9dc44a90521d4c2#7", b: "apple"},
  {a: "6a6be358b9dc44a90521d4c2#7", b: "eating"},
  {a: "6a6be358b9dc44a90521d4c2#7", b: "butterfly"},
  {a: "6a6be358b9dc44a90521d4c2#8", b: "tree"},
  {a: "6a6be358b9dc44a90521d4c2#8", b: "apple"},
  {a: "6a6be358b9dc44a90521d4c2#8", b: "eating"},
  {a: "6a6be358b9dc44a90521d4c2#9", b: "meadow"},
  {a: "6a6be358b9dc44a90521d4c2#9", b: "butterfly"},
  {a: "6a6be358b9dc44a90521d4c2#9", b: "nature"}
] AS row
MATCH (a:Segment {id: row.a})
MATCH (b:Topic {key: row.b})
MERGE (a)-[:ABOUT]->(b);

// --- (Segment)-[:MENTIONS]->(Entity) (29) ---
UNWIND [
  {a: "6a6be358b9dc44a90521d4c2#0", b: "forest"},
  {a: "6a6be358b9dc44a90521d4c2#0", b: "tree"},
  {a: "6a6be358b9dc44a90521d4c2#1", b: "tree"},
  {a: "6a6be358b9dc44a90521d4c2#1", b: "long-eared creature"},
  {a: "6a6be358b9dc44a90521d4c2#2", b: "rock"},
  {a: "6a6be358b9dc44a90521d4c2#2", b: "grassland"},
  {a: "6a6be358b9dc44a90521d4c2#2", b: "long-eared creature"},
  {a: "6a6be358b9dc44a90521d4c2#3", b: "sky"},
  {a: "6a6be358b9dc44a90521d4c2#3", b: "tree"},
  {a: "6a6be358b9dc44a90521d4c2#3", b: "long-eared creature"},
  {a: "6a6be358b9dc44a90521d4c2#4", b: "long-eared creature"},
  {a: "6a6be358b9dc44a90521d4c2#4", b: "flower"},
  {a: "6a6be358b9dc44a90521d4c2#5", b: "grass"},
  {a: "6a6be358b9dc44a90521d4c2#5", b: "long-eared creature"},
  {a: "6a6be358b9dc44a90521d4c2#5", b: "butterfly"},
  {a: "6a6be358b9dc44a90521d4c2#6", b: "butterfly"},
  {a: "6a6be358b9dc44a90521d4c2#6", b: "tree"},
  {a: "6a6be358b9dc44a90521d4c2#6", b: "long-eared creature"},
  {a: "6a6be358b9dc44a90521d4c2#6", b: "apple"},
  {a: "6a6be358b9dc44a90521d4c2#7", b: "butterfly"},
  {a: "6a6be358b9dc44a90521d4c2#7", b: "apple"},
  {a: "6a6be358b9dc44a90521d4c2#7", b: "apple tree"},
  {a: "6a6be358b9dc44a90521d4c2#7", b: "long-eared creature"},
  {a: "6a6be358b9dc44a90521d4c2#8", b: "long-eared creature"},
  {a: "6a6be358b9dc44a90521d4c2#8", b: "apple tree"},
  {a: "6a6be358b9dc44a90521d4c2#8", b: "apple"},
  {a: "6a6be358b9dc44a90521d4c2#9", b: "grassland"},
  {a: "6a6be358b9dc44a90521d4c2#9", b: "butterfly"},
  {a: "6a6be358b9dc44a90521d4c2#9", b: "long-eared creature"}
] AS row
MATCH (a:Segment {id: row.a})
MATCH (b:Entity {key: row.b})
MERGE (a)-[:MENTIONS]->(b);

// Everything, once loaded:
//   MATCH p=(v:Video)-[:HAS_SEGMENT]->(:Segment)-[:MENTIONS|ABOUT]->() RETURN p
// Entities shared by more than one video:
//   MATCH (v:Video)-[:HAS_SEGMENT]->(:Segment)-[:MENTIONS]->(e:Entity)
//   WITH e, count(DISTINCT v) AS n WHERE n > 1 RETURN e.name, e.type, n ORDER BY n DESC
