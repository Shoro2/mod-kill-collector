# mod-kill-collector

A May 2026 prototype ("Phase 1") of a kill-collection system: the first kill of every creature entry pays a
token item, and killing every creature entry of one creature type on a continent (open world plus its
dungeons and raids) grants a custom achievement. It was **never integrated into Forgotten Land**: it is not in
the workbench's module folder, not on the host, no vault document mentions it, and its seed data is
placeholder data whose ids partly collide with FL content (below). Full description: [README.md](README.md).

## Ids and tables

| What | Value | FL check (2026-10-09) |
|---|---|---|
| Token item | `item_template` **80001** "Hunter's Token" (`KillCollector.TokenItemId`); the base SQL deletes and re-inserts the row | **collision**: on the workbench 80001 is FL's "Venom Gland" (class 12, used by one creature loot row and one quest's required items) |
| Achievements | **30001-30040** (36 rows, `30000 + slot*10 + creature_type`), category 9000 | free in the server `Achievement.dbc` and in `achievement_dbc`; FL client patch-9 not checked; category 9000 not shipped; not in the vault's `06-custom-ids.md` |
| Criteria | **60001-60040**, type 68 | free server-side; type 68 is `ACHIEVEMENT_CRITERIA_TYPE_USE_GAMEOBJECT` in this core, not "SCRIPT_EVENT" as the JSON says |
| Characters DB | `mod_kill_collector_kills` (guid, entry), `mod_kill_collector_progress` (guid, continent, type) | not created on the workbench |
| World DB | `mod_kill_collector_continent_maps` (continents 0, 1, 530, 571 and their stock instances), `mod_kill_collector_totals` (36 buckets, placeholder `expected_total` 999999) | not created; FL's own maps (e.g. 727 Azealia) are not listed |
| C++ | `KillCollectorWorldScript`, `KillCollectorPlayerScript`, singleton `KillCollectorMgr` (`sKillCollectorMgr`) | never built against FL's core (not verified) |
| Config | `mod_kill_collector.conf`, `KillCollector.*` | not deployed |

## Status and progress

- Where it runs: nowhere. Not built (absent from `azerothcore-wotlk/modules`), not on the host, no MIG
  entry; players see nothing.
- Evidence: **T0** (code and placeholder data, 2026-05-06). The last commit message says the worldserver
  "builds, runs, and grants tokens immediately" - not verified for FL's core; there is no build or boot record.
- Done (prototype): kill hook with a per-player cache, token on a first kill, bucket progress and the
  achievement grant through `AchievementMgr::CompletedAchievement`, a placeholder seed that cannot complete
  any achievement, the generator `tools/generate_kill_collector_data.py`, DBC patch JSON for `patch_dbc.py`.

## Next steps

1. (suggestion) The operator decides whether FL wants a kill-collection system at all: no vault plan, queue
   row or decision exists for it.
2. Only then, before any build: clear the blockers in [todo.md](todo.md) - a free item id for the token,
   `creature.id` instead of `id1`, FL's maps in the continent table, a criterion type that cannot fire,
   registered achievement ids - and run the generator against FL's world DB.
3. README "Future Scope": an AIO progress window, the token vendor (`mod_kill_collector_npc.sql` is an empty
   placeholder), `.killcollector reset|backfill|stats`.

Open points in full: [todo.md](todo.md).

## Working here

- Branch `claude/<topic>-<sessionId>`, merge into `main` and push (project rule: no pull requests).
  Repository `Shoro2/mod-kill-collector`; the merged branch `claude/plan-kill-collector-module-5paoT` holds
  nothing beyond `main`.
- To try it: clone into `azerothcore-wotlk/modules/`, re-run CMake (a new module changes the source glob)
  and build in `C:\wowstuff\dcore_bin`. The next boot applies its base SQL - including the DELETE of item
  80001 - so fix the collision first. The repo's `CMakeLists.txt` is ignored by the core's module scan (it
  includes only `<module>.cmake`).
- New ids go through the vault registry `06-custom-ids.md`; achievement and criteria ids must stay at or
  below 65535 (smallint in the characters DB, vault `chronicle-raid/11-id-allocation.md`). Client DBC rows
  reach players only through the combined patch-9 builder (vault `13-bug-report-playbook.md` §3), not a
  separate `patch-K.MPQ` as the README suggests.
- Restart the workbench only with the workspace's `scripts\worldserver_restart.ps1` under
  `tools\shared.lock`; any deployment to the host needs a MIG entry in share-public
  `docs/World of Warcraft/forgotten-land/15-host-migration-log.md`.
- Vault: no document mentions this module; relevant are `06-custom-ids.md`, `09-db-tables.md`,
  `chronicle-raid/11-id-allocation.md`, `13-bug-report-playbook.md`.
- Doc set: INDEX.md, CLAUDE.md, data_structure.md, functions.md, log.md (newest first), todo.md.
