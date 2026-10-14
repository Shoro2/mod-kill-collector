# Todo

- (medium) T1 of the token shop (2026-10-15, never run): apply `mod_kill_collector_shop.sql` (item 920201), load
  fl-lua-scripts `TokenShop/` (`.reload ale`), run `kill_collector_shop` (a mage, slot 1), then look at the
  window and the hub entry with the client probe. Host: a MIG entry for the SQL, the Lua folder and the hub file.
- (low) The Hunter's Token (920200) shows no inventory icon: its display 6122 names none in `ItemDisplayInfo.dbc`.
  The shop falls back to a coin; a display with an icon (or a new row) would fix the bags too.
- (medium) T1 of the rewards (damage bonus, "N3rd", status lines; built and syntax-checked 2026-10-14, never
  run): CMake re-run (new source file), build, boot (errors log at its baseline; the new `chartitles_dbc` and
  `achievement_reward` rows load without a line), fl-pipeline 209 `--client` + patch-9, the scenarios
  `kill_collector_achievement`, `kill_collector_bonus` (a warlock, slot 2) and `kill_collector_meta` (slot 3):
  they reset the character's achievements themselves, so they can run again; `_meta` is the only test of the
  title, stacking and the login path ("N3rd" and the title bit 143 in `characters.knownTitles` are saved at
  logout: check it after the run).
- (medium) Operator: what the tokens buy (token vendor), and whether creatures of the other team's cities
  (guards without an NPC flag) belong in the humanoid lists.
- (medium) Host: MIG-118 (module) and MIG-119 (the client rows in the host patch-9) together in a window the
  operator approves; check first that `item_template` 920200 is free on the host; `AchievementsEnable = 1`
  only with both. The rewards add: the SQL rows `achievement_dbc` 30051, `chartitles_dbc` 178 (bit 143),
  `achievement_reward` 30051 (check on the host that 178 / 143 are free), the conf keys
  `KillCollector.DamageBonusPct` / `MetaAchievementId`, and the `CharTitles.dbc` row in the host patch-9.
- (low) The bonus covers melee swings, direct spell damage and periodic damage. Damage that goes around those
  hooks (damage shields, scripted `DealDamage`) is not raised. The bot scenario proves a direct spell on a
  creature of the same and another continent; melee, damage over time and a pet are not tested yet.
- (low) A reset of the achievements (the console's `.reset achievements`, the test bots' `resetachievements`) fires no hook: the bonus follows at the next login or `.killcollector status`.
  A game master's `.achievement add` of the last bucket achievement raises the bonus at once, but "N3rd" only at
  the next login.
- (low) The client's Reward texts name +5% (fl-pipeline 209 `REWARD_PCT`): another `KillCollector.DamageBonusPct`
  needs the constant changed and patch-9 rebuilt.
- (low) The achievements have no criteria rows, so the client shows no progress bar; `.killcollector status`
  is the progress view until an AIO window exists.
- (low) The lists follow the world database at startup: after content changes (new Turtle maps, spawns),
  `.killcollector reload` or a restart; a map that needs a continent override goes into
  `mod_kill_collector_continent_maps`.
