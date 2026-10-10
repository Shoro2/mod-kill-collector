# mod-kill-collector

Forgotten Land's creature collection: the first kill of every creature entry pays a Hunter's Token, and
killing every creature of one creature type on a continent grants an achievement (switched off until the
client patch ships). Every player the kill rewards collects the creature, the tapping group included. The
operator decided on 2026-10-10 to adopt the May 2026 prototype ("mod-kill-collector übernehmen"). Full
description: [README.md](README.md).

## Ids and tables

| What | Value |
|---|---|
| Token item | `item_template` **920200** "Hunter's Token" (FL item band 920200-920209 belongs to this module; `KillCollector.TokenItemId`) |
| Achievements | **30001-30050** = 30000 + 10 x continent slot (0 Eastern Kingdoms, 1 Kalimdor, 2 Outland, 3 Northrend, 4 Forgotten Land 727) + creature type (1-7, 9, 10); 45 rows in `mod_kill_collector_achievements`; category **15100** "Kill Collector" (top level), 10 points each, no criteria rows. Server rows: `achievement_dbc` (this module's SQL); client rows: FL's patch-9 (fl-pipeline `209_kill_collector_achievements.py`, which also writes the SQL) |
| Continents | 0, 1, 530, 571 and 727 (Forgotten Land): its own maps 727-753, 760 and 770 by override; every other map by its Map.dbc / `map_dbc` entrance map |
| Never counts | maps 13 (class test area), 451, 609 (death knight start), 754 (dev), every transport, battlegrounds and arenas |
| Characters DB | `mod_kill_collector_kills` (guid, entry, map_id, creature_type, first_kill_time) |
| World DB | `mod_kill_collector_continent_maps` (map_id, continent_id, comment; -1 = never counts), `mod_kill_collector_achievements` (continent_id, creature_type, achievement_id), three `command` rows |
| Commands | `.killcollector status` (players), `.killcollector reload` / `reset [name]` (administrators) |
| C++ | `KillCollectorMgr` (`sKillCollectorMgr`), `KillCollectorWorldScript`, `KillCollectorPlayerScript`, `KillCollectorCommandScript` |
| Config | `mod_kill_collector.conf`, `KillCollector.*` |

## Status and progress

- Where it runs: the workbench since 2026-10-10 03:07 local (worldserver sha256 `a037baa6…`, config
  `configs/modules/mod_kill_collector.conf`, achievements on since 03:19) and FL2-Client (patch-9 `df92c762…`
  with the achievement rows). Not on the host: vault MIG-118 (module) and MIG-119 (client rows), pending.
- Evidence: **T1** on the workbench 2026-10-10: build without warnings; boot with the four SQL files applied
  and the errors log at its 87-line baseline; the lists per team as estimated offline (Eastern Kingdoms
  2218 Alliance / 2415 Horde, Kalimdor 1728 / 1737, Outland 1583 / 1577, Northrend 1575 / 1611, Forgotten
  Land 262 / 262); bot run 583 of `kill_collector_tokens` PASSED 19/0 (first kill pays killer and party
  member, a repeated entry pays nothing, a new entry pays again, `.killcollector status / reset`); bot run
  584 of `kill_collector_achievement` PASSED 11/0 (completing "Oddities of the Forgotten Land" granted
  30050, saved in `character_achievement`); the probe client (CRTEST1) lists the "Kill Collector" category
  with its 45 achievements. No T2.
- Done in the adoption: FL item id; `creature.id` (FL) instead of `id1`; FL's maps as a fifth continent;
  continent resolution by override, then the map's entrance; per-team lists of attackable creatures (no
  event-only, phased, unattackable, trigger or NPC-flag spawns); progress computed from the kills at login
  (no stored counters); the group collects through `OnPlayerRewardKillRewarder`; tokens by mail when the
  bags are full; a mutex for map threads; the kills of a deleted character go with it; `.killcollector`
  commands; achievements without criteria rows (the prototype's criterion type 68 could have fired on a
  gameobject use); placeholder totals, the old generator and the DBC JSON removed.

## Next steps

1. The operator decides what the tokens buy (a token vendor) and whether enemy-city creatures belong in the
   lists.
2. Host: MIG-118 and MIG-119 together in a window the operator approves (achievements on only with both).

Open points in full: [todo.md](todo.md).

## Working here

- Branch `claude/<topic>-<sessionId>`, merge into `main` and push (project rule: no pull requests).
- The workbench builds it from `azerothcore-wotlk/modules/mod-kill-collector` (on `main`) since 2026-10-10.
- New ids go through the vault registry `06-custom-ids.md`; achievement ids stay at or below 65535
  (smallint in the characters DB). Client DBC rows reach players only through the combined patch-9 builder.
- Restart the workbench only with `scripts\worldserver_restart.ps1`; any host deployment needs a MIG entry
  in share-public `docs/World of Warcraft/forgotten-land/15-host-migration-log.md`.
- Tests: `tests/kill_collector_tokens.tbs` (bots, TBOT accounts).
- Doc set: INDEX.md, CLAUDE.md, data_structure.md, functions.md, log.md (newest first), todo.md.
