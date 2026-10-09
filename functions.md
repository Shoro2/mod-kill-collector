# Functions

Prototype code (2026-05-06), never built or run on Forgotten Land; everything below is from reading the code.

## Scripts and lifecycle

| Script | Hook | What |
|---|---|---|
| `KillCollectorWorldScript` | `OnAfterConfigLoad(bool)` | `LoadConfig()`; when enabled also `LoadCachesFromWorldDB()` (so `.reload config` reloads the caches too) |
| `KillCollectorPlayerScript` | `OnPlayerLogin(Player*)` | `LoadPlayerStateOnLogin`: the character's killed entries and bucket counts into memory (only while enabled) |
| | `OnPlayerLogout(Player*)` | `FlushPlayerStateOnLogout`: drops the cache (rows are written at kill time) |
| | `OnPlayerCreatureKill(Player* killer, Creature* killed)` | `HandleCreatureKill` |

`KillCollectorMgr` is a function-local static singleton (`KillCollectorMgr::instance()`, macro
`sKillCollectorMgr`).

## Caches (`LoadCachesFromWorldDB`)

- `_mapToContinent` from `mod_kill_collector_continent_maps`.
- `_expectedTotals` and `_achievementByBucket` from `mod_kill_collector_totals`, keyed by
  `BucketKey(continent, type) = continent << 8 | type`.
- `_expectedMobs`: distinct `creature_template.entry` per bucket that have a spawn on a tracked map, types 1-7,
  9, 10 - the query joins `creature c ON c.id1 = ct.entry`. **FL's core and world DB name that column `id`**,
  so on FL this query fails and the set stays empty (see todo).
- Logs `>> KillCollector: loaded <maps> continent-map mappings, <buckets> buckets, <entries> expected mob
  entries.` and a warning while any bucket total is at or above the sentinel 999999.

## The kill (`HandleCreatureKill`)

1. Return unless enabled and `PassesFilters`: no pets or totems; critters, totems and non-combat pets only
   when their `Include*` key is on; open world / instances by `IncludeOpenWorld` / `IncludeInstances`
   (`Map::Instanceable()`); hostile to the killer when `RequireHostile`; `victim level - killer level >=
   MinLevelDelta` unless `MinLevelDelta` is -100 or lower.
2. Continent = the killer's map through `_mapToContinent` (unknown map: no achievement progress).
3. A repeat kill of the same entry returns; a first kill: `INSERT IGNORE` into `mod_kill_collector_kills`,
   `AddItem(TokenItemId, TokensPerFirstKill)`, chat line `[Kill Collector] New unique kill! +<n> token.`
   when `AnnounceFirstKill`.
4. Achievements (if `AchievementsEnable` and the entry belongs to the bucket's expected set): increment the
   bucket count, upsert `mod_kill_collector_progress`; when the count reaches a real total (below 999999)
   `TryCompleteAchievement` looks the id up in `sAchievementStore` (a missing DBC row logs a warning) and calls
   `GetAchievementMgr()->CompletedAchievement`.

All SQL is plain formatted strings with numeric values from the server (no prepared statements, no player
text).

## Achievement layout

`achievement_id = AchievementIdBase + slot * 10 + creature_type`, slots 0 Eastern Kingdoms, 1 Kalimdor,
2 Outland, 3 Northrend, creature types 1-7, 9, 10 (8 = critter skipped) -> 30001-30040, criteria
60001-60040 with the same offsets. Each achievement has one dummy criterion; completion is forced by the
server, so the client only needs the DBC rows to display it.

## Generator (`tools/generate_kill_collector_data.py`)

Python with `mysql-connector-python`; flags `--host --port --user --password --database`,
`--achievement-base` (30000), `--criteria-base` (60000), `--category-id` (9000), `--out-sql`, `--out-ach`,
`--out-cri`, `--include-empty`. Counts the distinct spawned entries per bucket (same `c.id1` join) and writes
`data/sql/db-world/updates/mod_kill_collector_totals_seed.sql` plus the two DBC patch JSON files.

## Config

Keys and defaults: [data_structure.md](data_structure.md).
