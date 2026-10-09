# mod-kill-collector

Forgotten Land's creature collection: the first kill of every creature entry pays a Hunter's Token, and
killing every creature of one creature type on a continent grants an achievement (switched off until the
client patch ships). Every player the kill rewards collects the creature, the tapping group included. The
operator decided on 2026-10-10 to adopt the May 2026 prototype ("mod-kill-collector übernehmen"); this
branch is that adoption. Full description: [README.md](README.md).

## Ids and tables

| What | Value |
|---|---|
| Token item | `item_template` **920200** "Hunter's Token" (FL item band 920200-920209 belongs to this module; `KillCollector.TokenItemId`) |
| Achievements | **30001-30050** = 30000 + 10 x continent slot (0 Eastern Kingdoms, 1 Kalimdor, 2 Outland, 3 Northrend, 4 Forgotten Land 727) + creature type (1-7, 9, 10); 45 rows in `mod_kill_collector_achievements`. Server and client `Achievement.dbc` rows are not written yet |
| Continents | 0, 1, 530, 571 and 727 (Forgotten Land): its own maps 727-753, 760 and 770 by override; every other map by its Map.dbc / `map_dbc` entrance map |
| Never counts | maps 13 (class test area), 451, 609 (death knight start), 754 (dev), every transport, battlegrounds and arenas |
| Characters DB | `mod_kill_collector_kills` (guid, entry, map_id, creature_type, first_kill_time) |
| World DB | `mod_kill_collector_continent_maps` (map_id, continent_id, comment; -1 = never counts), `mod_kill_collector_achievements` (continent_id, creature_type, achievement_id), three `command` rows |
| Commands | `.killcollector status` (players), `.killcollector reload` / `reset [name]` (administrators) |
| C++ | `KillCollectorMgr` (`sKillCollectorMgr`), `KillCollectorWorldScript`, `KillCollectorPlayerScript`, `KillCollectorCommandScript` |
| Config | `mod_kill_collector.conf`, `KillCollector.*` |

## Status and progress

- Where it runs: nowhere yet. Not in the workbench's `azerothcore-wotlk/modules`, not on the host, no MIG
  entry.
- Evidence: **T0** (code and data on branch `claude/kill-collector-adopt-433902b4`, 2026-10-10). Not built:
  the workbench was reserved for HOST11. The bucket sizes were measured offline with the module's rules on
  the workbench data (2026-10-10, per team): Eastern Kingdoms ~2,200-2,400 creatures, Kalimdor ~1,730,
  Outland ~1,580, Northrend ~1,600, Forgotten Land 262.
- Done in the adoption: FL item id; `creature.id` (FL) instead of `id1`; FL's maps as a fifth continent;
  continent resolution by override, then the map's entrance; per-team lists of attackable creatures (no
  event-only, phased, unattackable, trigger or NPC-flag spawns); progress computed from the kills at login
  (no stored counters); the group collects through `OnPlayerRewardKillRewarder`; tokens by mail when the
  bags are full; a mutex for map threads; the kills of a deleted character go with it; `.killcollector`
  commands; achievements without criteria rows (the prototype's criterion type 68 could have fired on a
  gameobject use); placeholder totals, the old generator and the DBC JSON removed.

## Next steps

1. After HOST11, in a workbench slot from the coordinator: clone into `azerothcore-wotlk/modules`, cmake,
   build, boot (errors log = the 87 baseline lines), deploy `mod_kill_collector.conf`, add `tests/` to
   `TestBots.ScenarioDirs`, run `kill_collector_tokens`; then merge into `main`.
2. Achievements: write the 45 rows (or only the non-empty buckets) into the client's `Achievement.dbc`
   through the combined patch-9 builder, plus a category, and into `achievement_dbc`; check the ids
   against patch-9 first; then `AchievementsEnable = 1`.
3. The operator decides what the tokens buy (a token vendor) and whether enemy-city creatures belong in the
   lists.
4. Host: its own MIG entry and a window the operator approves.

Open points in full: [todo.md](todo.md).

## Working here

- Branch `claude/<topic>-<sessionId>`, merge into `main` and push (project rule: no pull requests).
- Never clone it into `azerothcore-wotlk/modules` outside an agreed workbench slot: the next build and boot
  of any session would pick it up and apply its SQL.
- New ids go through the vault registry `06-custom-ids.md`; achievement ids stay at or below 65535
  (smallint in the characters DB). Client DBC rows reach players only through the combined patch-9 builder.
- Restart the workbench only with `scripts\worldserver_restart.ps1`; any host deployment needs a MIG entry
  in share-public `docs/World of Warcraft/forgotten-land/15-host-migration-log.md`.
- Tests: `tests/kill_collector_tokens.tbs` (bots, TBOT accounts).
- Doc set: INDEX.md, CLAUDE.md, data_structure.md, functions.md, log.md (newest first), todo.md.
