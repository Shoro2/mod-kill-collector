# Todo

- (high) Build, boot and test on the workbench (after HOST11, in a slot from the coordinator): clone into
  `azerothcore-wotlk/modules`, cmake, build; the boot's errors log must stay at its baseline; deploy
  `mod_kill_collector.conf`; add `tests/` to `TestBots.ScenarioDirs`; run `kill_collector_tokens`; check the
  ">> KillCollector: continent ..." lines against the offline estimate (2026-10-10: Eastern Kingdoms
  2218 Alliance / 2415 Horde, Kalimdor 1728 / 1737, Outland 1583 / 1577, Northrend 1575 / 1611, Forgotten
  Land 262 / 262). Then merge into `main`.
- (high) Achievements: client `Achievement.dbc` rows 30001-30050 (only the non-empty buckets), an
  `Achievement_Category` row, names and descriptions, through the combined patch-9 builder; the same rows in
  `achievement_dbc` on the server; check the ids against patch-9 first. No criteria rows are needed (the
  module completes the achievement itself). Then `AchievementsEnable = 1`.
- (medium) Operator: what the tokens buy (token vendor), and whether creatures of the other team's cities
  (guards without an NPC flag) belong in the humanoid lists.
- (medium) Host: a MIG entry and a window the operator approves; check that `item_template` 920200 is free
  on the host first.
- (low) A test that the mail fallback works (bags full).
- (low) The lists follow the world database at startup: after content changes (new Turtle maps, spawns),
  `.killcollector reload` or a restart; a map that needs a continent override goes into
  `mod_kill_collector_continent_maps`.
