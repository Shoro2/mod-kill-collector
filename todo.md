# Todo

- (high) Achievements: client `Achievement.dbc` rows 30001-30050 (only the non-empty buckets), an
  `Achievement_Category` row, names and descriptions, through the combined patch-9 builder; the same rows in
  `achievement_dbc` on the server; check the ids against patch-9 first. No criteria rows are needed (the
  module completes the achievement itself). Then `AchievementsEnable = 1`.
- (medium) Operator: what the tokens buy (token vendor), and whether creatures of the other team's cities
  (guards without an NPC flag) belong in the humanoid lists.
- (medium) Host: MIG-118 (vault) in a window the operator approves; check first that `item_template` 920200
  is free on the host.
- (low) A test that the mail fallback works (bags full).
- (low) The lists follow the world database at startup: after content changes (new Turtle maps, spawns),
  `.killcollector reload` or a restart; a map that needs a continent override goes into
  `mod_kill_collector_continent_maps`.
