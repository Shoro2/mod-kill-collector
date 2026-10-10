# Todo

- (medium) Operator: what the tokens buy (token vendor), and whether creatures of the other team's cities
  (guards without an NPC flag) belong in the humanoid lists.
- (medium) Host: MIG-118 (module) and MIG-119 (the client rows in the host patch-9) together in a window the
  operator approves; check first that `item_template` 920200 is free on the host; `AchievementsEnable = 1`
  only with both.
- (low) The achievements have no criteria rows, so the client shows no progress bar; `.killcollector status`
  is the progress view until an AIO window exists.
- (low) A test that the mail fallback works (bags full).
- (low) The lists follow the world database at startup: after content changes (new Turtle maps, spawns),
  `.killcollector reload` or a restart; a map that needs a continent override goes into
  `mod_kill_collector_continent_maps`.
