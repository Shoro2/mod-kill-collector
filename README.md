# mod-kill-collector

AzerothCore WotLK module for Forgotten Land: players collect creatures. The first kill of every creature
entry pays a token, and - once the client patch is out - killing every creature of one creature type on a
continent grants an achievement.

## What it does

- **Unique kills.** Each (character, creature entry) pair counts once. Every player the kill rewards
  collects the creature: the killer, the members of the tapping group within reward distance, also when a
  pet or totem landed the blow. Kills in battlegrounds and arenas, of critters, totems and non-combat pets,
  and kills by a game master in GM mode do not count.
- **Tokens.** A first kill pays `KillCollector.TokensPerFirstKill` Hunter's Tokens (item 920200). What does
  not fit into the bags arrives by mail.
- **Achievements** (off until the client patch ships). One per continent and creature type: Eastern
  Kingdoms, Kalimdor, Outland, Northrend and Forgotten Land (Azealia, its dungeons and raids, the Forgotten
  Depths and the Endless Chronicle), each with beasts, dragonkin, demons, elementals, giants, undead,
  humanoids, mechanicals and unspecified creatures. The list of a bucket is computed at startup from the
  world database: every creature entry spawned on the continent - its dungeons and raids included - that
  the player's team can attack. Spawns that only exist during a game event or outside the normal phase,
  unattackable creatures, triggers and (by default) creatures with an NPC flag stay out, so every list can
  be completed.
- **`.killcollector status`** shows the number of collected creatures and the progress per continent;
  `.killcollector reset [name]` (administrators) empties a collection, `.killcollector reload` rebuilds the
  lists.

## Installation

1. Clone into `azerothcore-wotlk/modules/mod-kill-collector/`, re-run CMake (a new module adds sources) and
   build the worldserver.
2. The SQL under `data/sql/db-characters/base/` and `data/sql/db-world/base/` is applied by the core's
   updater at the next start.
3. Copy `conf/mod_kill_collector.conf.dist` to `mod_kill_collector.conf` and adjust it.
4. Achievements: ship the `Achievement.dbc` rows (ids 30001-30050) in the client patch and on the server
   (`Achievement.dbc` or `achievement_dbc`), then set `KillCollector.AchievementsEnable = 1`.

## Configuration

See `conf/mod_kill_collector.conf.dist` for every option.

## Schema

Characters DB: `mod_kill_collector_kills` - one row per (character, entry).

World DB: `mod_kill_collector_continent_maps` (maps whose continent the Map.dbc entrance does not give, or
that never count), `mod_kill_collector_achievements` (continent, creature type -> achievement id),
`item_template` 920200, three `command` rows.
