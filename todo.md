# Todo

The module was never integrated; these are the blockers found on 2026-10-09 against the workbench, to clear
before any build on FL (and only if the operator wants the system at all).

- (high) Item id collision: `data/sql/db-world/base/mod_kill_collector_item.sql` deletes and re-inserts
  `item_template` 80001, which on FL is "Venom Gland" (class 12, used by one creature loot row and one quest's
  required items on the workbench). Pick a free id from the vault registry `06-custom-ids.md` and change
  `KillCollector.TokenItemId`, `DEFAULT_TOKEN_ITEM_ID` and the SQL together.
- (high) `LoadCachesFromWorldDB` and the generator join `creature.id1`; FL's core and world DB use
  `creature.id`. Enabled as is, the expected-mob query fails at startup, tokens still pay out and no
  achievement can ever progress.
- (medium) `mod_kill_collector_continent_maps` lists only the stock continents 0, 1, 530, 571 and their
  instances; FL's own maps (e.g. 727 Azealia) give tokens but no achievement progress. Decide FL's
  "continents" first.
- (medium) The criteria JSON uses type 68 as a never-firing "SCRIPT_EVENT"; in this core 68 is
  `ACHIEVEMENT_CRITERIA_TYPE_USE_GAMEOBJECT` (`DBCEnums.h`). Its asset ids (1-10, 101-110, 53001-53010,
  57101-57110) include existing gameobject templates (4 and 101-110 on the workbench), so once the rows ship,
  using such an object could complete an achievement through the stock criteria engine. Choose a type that
  cannot fire; also fix the comment in `tools/README.md`.
- (medium) Achievements 30001-30040 and criteria 60001-60040 are free on the workbench server side
  (`Achievement.dbc`, `Achievement_Criteria.dbc`, the two `*_dbc` tables); the FL client's patch-9 was not
  checked, category 9000 has no `Achievement_Category` row, and none of the ids is registered in
  `06-custom-ids.md`.
- (low) `data/dbc/README.md` "ID assignments" says 30000..30039; the JSON, the SQL and the generator use
  30001..30040 (`base + slot * 10 + creature_type`).
- (low) `KillCollector.CountPetKills` is read but never used.
- (low) Every bucket total is the placeholder 999999 until the generator runs against FL's world DB (after
  the `id` fix).
