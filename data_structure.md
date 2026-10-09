# Data structure

| Path | What |
|---|---|
| `README.md` | Phase-1 features, future scope, placeholders, install, schema |
| `CMakeLists.txt` | old-style `mod-kill-collector_STAT_SRCS` glob; the core's module scan ignores it |
| `conf/mod_kill_collector.conf.dist` | the `KillCollector.*` keys |
| `src/mod_kill_collector_loader.cpp` | `Addmod_kill_collectorScripts()` -> `AddKillCollectorScripts()` |
| `src/kill_collector.cpp` | `AddKillCollectorScripts()`: world script first, then the player script |
| `src/kill_collector_common.h` | includes, `DEFAULT_TOKEN_ITEM_ID` 80001, `DEFAULT_ACHIEVEMENT_ID_BASE` 30000, `BucketKey(continent, type)` |
| `src/kill_collector_manager.h/.cpp` | `KillCollectorMgr`: config, caches, filters, token, progress, achievements, persistence |
| `src/kill_collector_world_script.cpp` | `KillCollectorWorldScript` (`OnAfterConfigLoad`) |
| `src/kill_collector_player_script.cpp` | `KillCollectorPlayerScript` (login, logout, creature kill) |
| `data/sql/db-characters/base/mod_kill_collector_characters.sql` | the two characters tables |
| `data/sql/db-world/base/mod_kill_collector_item.sql` | DELETE + INSERT `item_template` 80001 "Hunter's Token" (class 15, quality 4, stack 1000, display 6122) |
| `data/sql/db-world/base/mod_kill_collector_npc.sql` | comment only: the Phase-2 vendor placeholder |
| `data/sql/db-world/base/mod_kill_collector_totals.sql` | the two world tables + the continent-map seed |
| `data/sql/db-world/base/mod_kill_collector_totals_placeholder.sql` | 36 bucket rows with `expected_total` 999999 |
| `data/dbc/Achievement.dbc.patch.json`, `Achievement_Criteria.dbc.patch.json` | 36 + 36 placeholder rows for share-public `python_scripts/patch_dbc.py` |
| `data/dbc/README.md` | DBC workflow and the id layout (its table is off by one, see todo) |
| `tools/generate_kill_collector_data.py`, `tools/README.md` | generator for the real totals seed and the DBC JSON |

## Tables

| Table | DB | Columns / key |
|---|---|---|
| `mod_kill_collector_kills` | characters | `guid`, `entry`, `map_id`, `creature_type`, `first_kill_time`; PK (`guid`, `entry`) |
| `mod_kill_collector_progress` | characters | `guid`, `continent_id`, `creature_type`, `kill_count`, `completed_at`; PK (`guid`, `continent_id`, `creature_type`) |
| `mod_kill_collector_continent_maps` | world | `continent_id`, `map_id`; PK both (0 Eastern Kingdoms, 1 Kalimdor, 530 Outland, 571 Northrend, each with its stock dungeons and raids) |
| `mod_kill_collector_totals` | world | `continent_id`, `creature_type`, `expected_total`, `achievement_id`; PK (`continent_id`, `creature_type`) |

None of them exists on the workbench (checked 2026-10-09).

## Config keys (`mod_kill_collector.conf`)

| Key | Default (conf / code) | Meaning |
|---|---|---|
| `KillCollector.Enable` | 1 / false | master switch |
| `KillCollector.TokenItemId` | 80001 | token item |
| `KillCollector.TokensPerFirstKill` | 1 | tokens per first kill |
| `KillCollector.AnnounceFirstKill` | 1 | chat line on a first kill |
| `KillCollector.IncludeOpenWorld` / `IncludeInstances` | 1 / 1 | where kills count |
| `KillCollector.IncludeCritters` / `IncludeTotems` / `IncludeNonCombatPets` | 0 / 0 / 0 | creature types that count |
| `KillCollector.RequireHostile` | 1 | only creatures hostile to the killer |
| `KillCollector.MinLevelDelta` | -10 | skip when `victim level - player level` is lower; -100 turns the filter off |
| `KillCollector.CountPetKills` | 1 | read but never used by the code |
| `KillCollector.AchievementsEnable` | 1 | grant achievements |
| `KillCollector.AchievementIdBase` | 30000 | informational; the mapping lives in `mod_kill_collector_totals` |
| `KillCollector.LogVerbose` | 0 | one log line per counted kill |
