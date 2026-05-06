# mod-kill-collector

AzerothCore WotLK module that rewards players for collecting unique creature kills and grants real DBC achievements when they have killed every creature of a given `CreatureType` on a continent (open world plus dungeons/raids).

## Features (Phase 1)

- **Unique-kill tracking**: Each `(player, creature_template.entry)` pair is recorded once. Repeat kills of the same entry give nothing.
- **Custom currency token**: First kill of a new entry awards a configurable item (default `item_template.entry = 80001` "Hunter's Token").
- **Per-continent achievements**: When a player has at least one kill of every expected entry of a given `CreatureType` on a continent, the matching achievement (real DBC entry) is granted via `AchievementMgr::CompletedAchievement`.
- **Continent grouping**: A `mod_kill_collector_continent_maps` table folds dungeon/raid `map_id`s into their parent continent, so instance kills count.

## Future Scope (later phases)

- AIO-Lua client UI showing per-continent progress and missing entries.
- Vendor NPC that exchanges tokens for rewards (mounts, transmog, consumables).
- GM commands (`.killcollector reset|backfill|stats`).

## Placeholders

The module ships with **placeholder seed data** so it builds and runs out of the box without an external generator step. Specifically:

- `data/sql/db-world/base/mod_kill_collector_totals_placeholder.sql` populates `mod_kill_collector_totals` with all 36 buckets (4 continents x 9 creature types). Every `expected_total` is the sentinel value **999999**, which is large enough that no continent will ever satisfy the threshold by accident.
- `data/dbc/Achievement.dbc.patch.json` and `data/dbc/Achievement_Criteria.dbc.patch.json` contain the corresponding 36 + 36 placeholder rows ready for `patch_dbc.py`. IDs already follow the canonical layout (`30000 + slot * 10 + creature_type`), so you can ship the patched DBCs immediately and only the totals need to be updated later.

When the worldserver loads, the manager logs a `LOG_WARN` for every placeholder bucket - watch your log for the line:

```
>> KillCollector: 36 of 36 bucket totals are PLACEHOLDERS (>= 999999). ...
```

Replace the placeholders by running the generator against your live world DB:

```bash
pip install mysql-connector-python
python3 tools/generate_kill_collector_data.py \
    --user acore --password acore --database acore_world
mysql -u acore -p acore_world < data/sql/db-world/updates/mod_kill_collector_totals_seed.sql
```

Then re-patch the DBCs from the regenerated JSON files (see `data/dbc/README.md`) and restart the worldserver. The warning disappears once every bucket has a real total.

## Installation

1. Clone this repo into `azerothcore-wotlk/modules/mod-kill-collector/`.
2. Re-run CMake and rebuild the worldserver.
3. SQL files in `data/sql/db-characters/base/` and `data/sql/db-world/base/` are auto-imported by AzerothCore on startup.
4. Copy the patched DBCs from `data/dbc/` (after running `patch_dbc.py`) into `azerothcore-wotlk/data/dbc/`.
5. Distribute the matching `patch-K.MPQ` to clients (place in `WoW/Data/`).
6. Edit `conf/mod_kill_collector.conf` (copy from `.conf.dist`).

## Configuration

See `conf/mod_kill_collector.conf.dist` for all options.

## Schema

Characters DB:
- `mod_kill_collector_kills` - one row per (guid, entry).
- `mod_kill_collector_progress` - one row per (guid, continent_id, creature_type).

World DB:
- `mod_kill_collector_continent_maps` - mapId -> continent grouping.
- `mod_kill_collector_totals` - expected total entries and achievement_id per (continent, creature_type).
- `item_template` row 80001 - the token item.
