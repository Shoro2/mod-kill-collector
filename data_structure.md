# Data structure

## Files

| File | Content |
|---|---|
| `src/kill_collector_common.h` | `DEFAULT_TOKEN_ITEM_ID` 920200, `META_ACHIEVEMENT_ID` 30051, `DEFAULT_DAMAGE_BONUS_PCT` 5, the team count, the player faction templates 1 / 2, `EXCLUDED_MAP` -1, `BucketKey(continent, type)`, `KillCollectorBonus` (the damage bonus on the Player), `CreatureTypePlural` |
| `src/kill_collector_manager.h/.cpp` | `KillCollectorMgr`: config, the data (continents, buckets, expected sets), the online players' collections, tokens, achievements, the damage bonus and the meta achievement |
| `src/kill_collector_player_script.cpp` | login, logout, kill reward, achievement completed, character deletion |
| `src/kill_collector_unit_script.cpp` | `KillCollectorUnitScript`: the damage hooks (melee, direct spell, periodic damage) |
| `src/kill_collector_world_script.cpp` | config load, startup |
| `src/kill_collector_command_script.cpp` | `.killcollector status / reload / reset` |
| `src/kill_collector.cpp`, `src/mod_kill_collector_loader.cpp` | registration; `Addmod_kill_collectorScripts()` |
| `data/sql/db-characters/base/mod_kill_collector_characters.sql` | `mod_kill_collector_kills` |
| `data/sql/db-world/base/mod_kill_collector_world.sql` | `mod_kill_collector_continent_maps` (56 rows), `mod_kill_collector_achievements` (45 rows) |
| `data/sql/db-world/base/mod_kill_collector_item.sql` | `item_template` 920200 (DELETE + INSERT) |
| `data/sql/db-world/base/mod_kill_collector_achievement_dbc.sql` | `achievement_dbc` 30001-30051, `chartitles_dbc` 178, `achievement_reward` 30051 (DELETE + INSERT; written by fl-pipeline 209) |
| `data/sql/db-world/base/mod_kill_collector_command.sql` | `command` rows `killcollector status / reload / reset` |
| `conf/mod_kill_collector.conf.dist` | every config key with its default |
| `tests/kill_collector_tokens.tbs` | bot scenario: first kills, the party, a repeated entry |
| `tests/kill_collector_edges.tbs` | bot scenario: relog, reload, full bags (the token by mail) |
| `tests/kill_collector_achievement.tbs` | bot scenario: the three Oddities of the Forgotten Land complete their list, achievement 30050, the status lines of the bonus and of "N3rd" |
| `tests/kill_collector_bonus.tbs` | bot scenario: the combat log shows 4000 without and 4200 with the Oddities achievement (fixed damage spell 37463), also on another continent; a beast stays at 4000; spell 66595 (ignores the caster's modifiers) stays at 5000 |
| `tests/kill_collector_meta.tbs` | bot scenario: 44 achievements by game master command stack to +20% / +25% (4800 in the combat log), the 45th by the kills completes "N3rd" and gives 5000; a second part: all 45 by command, "N3rd" comes with the next login |

Every SQL file is idempotent (`CREATE TABLE IF NOT EXISTS`, `DELETE` + `INSERT`): the core's updater
applies a module file again whenever its bytes change.

## Tables

| Table | Key | Columns |
|---|---|---|
| `acore_characters.mod_kill_collector_kills` | (`guid`, `entry`) | `map_id` and `creature_type` of the first kill, `first_kill_time` (unix) |
| `acore_world.mod_kill_collector_continent_maps` | `map_id` | `continent_id` (a continent of the achievements table, -1 = never counts), `comment` |
| `acore_world.mod_kill_collector_achievements` | (`continent_id`, `creature_type`) | `achievement_id` (unique) |
| `acore_world.achievement_dbc` | `ID` | the module's rows 30001-30051 (server copy of Achievement.dbc; no criteria rows) |
| `acore_world.chartitles_dbc` | `ID` | row 178 "N3rd %s" (`Name_Lang_enUS`, `Name1_Lang_enUS`), `Mask_ID` 143 |
| `acore_world.achievement_reward` | `ID` | row 30051: `TitleA` = `TitleH` = 178, no item, no mail |

The continent overrides: Forgotten Land's maps 727, 729, 733-753, 760, 770 -> 727; maps 13, 451, 609, 754
and the 27 transports -> -1. Any other map: the map itself if it is a continent, else its entrance map
(Map.dbc / `map_dbc` `CorpseMapID`), else it never counts; battlegrounds and arenas never count.

## The damage bonus on the Player

`Player::CustomData["kill-collector"]` holds a `KillCollectorBonus`: `earned[16]`, indexed by CreatureType = the
number of earned bucket achievements of that type (at most five with the default lists). The manager writes it
- at login (after the achievements are granted), after it granted a bucket achievement, when any bucket
achievement completes (also a game master's `.achievement add`), and in `.killcollector status` - and the
damage hooks only read it, so they take no lock. The percentage is `earned` x `KillCollector.DamageBonusPct`,
read at the blow. `.reset achievements` fires no hook: the status command or the next login rereads it.

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
| `KillCollector.DamageBonusPct` | 5 | percent damage against a creature type per earned achievement of that type (0 = no bonus, at most 100); independent of `AchievementsEnable`. The client's Reward text (209 `REWARD_PCT`) names 5 |
| `KillCollector.MetaAchievementId` | 30051 | the "N3rd" achievement, 0 = none; needs `AchievementsEnable` |
| `KillCollector.LogVerbose` | 0 | log every collected creature |
