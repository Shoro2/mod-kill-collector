# Data structure

## Files

| File | Content |
|---|---|
| `src/kill_collector_common.h` | `DEFAULT_TOKEN_ITEM_ID` 920200, the team count, the player faction templates 1 / 2, `EXCLUDED_MAP` -1, `BucketKey(continent, type)` |
| `src/kill_collector_manager.h/.cpp` | `KillCollectorMgr`: config, the data (continents, buckets, expected sets), the online players' collections, tokens, achievements |
| `src/kill_collector_player_script.cpp` | login, logout, kill reward, character deletion |
| `src/kill_collector_world_script.cpp` | config load, startup |
| `src/kill_collector_command_script.cpp` | `.killcollector status / reload / reset` |
| `src/kill_collector.cpp`, `src/mod_kill_collector_loader.cpp` | registration; `Addmod_kill_collectorScripts()` |
| `data/sql/db-characters/base/mod_kill_collector_characters.sql` | `mod_kill_collector_kills` |
| `data/sql/db-world/base/mod_kill_collector_world.sql` | `mod_kill_collector_continent_maps` (56 rows), `mod_kill_collector_achievements` (45 rows) |
| `data/sql/db-world/base/mod_kill_collector_item.sql` | `item_template` 920200 (DELETE + INSERT) |
| `data/sql/db-world/base/mod_kill_collector_achievement_dbc.sql` | `achievement_dbc` 30001-30050 (DELETE + INSERT; written by fl-pipeline 209) |
| `data/sql/db-world/base/mod_kill_collector_command.sql` | `command` rows `killcollector status / reload / reset` |
| `conf/mod_kill_collector.conf.dist` | every config key with its default |
| `tests/kill_collector_tokens.tbs` | bot scenario: first kills, the party, a repeated entry |
| `tests/kill_collector_achievement.tbs` | bot scenario: the three Oddities of the Forgotten Land complete their list, achievement 30050 |

Every SQL file is idempotent (`CREATE TABLE IF NOT EXISTS`, `DELETE` + `INSERT`): the core's updater
applies a module file again whenever its bytes change.

## Tables

| Table | Key | Columns |
|---|---|---|
| `acore_characters.mod_kill_collector_kills` | (`guid`, `entry`) | `map_id` and `creature_type` of the first kill, `first_kill_time` (unix) |
| `acore_world.mod_kill_collector_continent_maps` | `map_id` | `continent_id` (a continent of the achievements table, -1 = never counts), `comment` |
| `acore_world.mod_kill_collector_achievements` | (`continent_id`, `creature_type`) | `achievement_id` (unique) |

The continent overrides: Forgotten Land's maps 727, 729, 733-753, 760, 770 -> 727; maps 13, 451, 609, 754
and the 27 transports -> -1. Any other map: the map itself if it is a continent, else its entrance map
(Map.dbc / `map_dbc` `CorpseMapID`), else it never counts; battlegrounds and arenas never count.

## Config keys

| Key | Default | Meaning |
|---|---|---|
| `KillCollector.Enable` | 1 | master switch |
| `KillCollector.TokenItemId` | 920200 | token item, 0 = none |
| `KillCollector.TokensPerFirstKill` | 1 | tokens per first kill |
| `KillCollector.AnnounceFirstKill` | 1 | chat line per collected creature |
| `KillCollector.IncludeOpenWorld` / `IncludeInstances` | 1 / 1 | which maps count |
| `KillCollector.IncludeCritters` / `IncludeTotems` / `IncludeNonCombatPets` | 0 / 0 / 0 | which types count |
| `KillCollector.MinLevelDelta` | -100 | skip kills of creatures this far below the player; -100 = off |
| `KillCollector.AchievementsEnable` | 0 | grant achievements (needs the DBC rows) |
| `KillCollector.Expected.SkipNpcFlagCreatures` | 1 | keep NPC-flag creatures out of the lists |
| `KillCollector.LogVerbose` | 0 | log every collected creature |
