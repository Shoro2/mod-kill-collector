# mod-kill-collector tools

## generate_kill_collector_data.py

Generates the bucket-totals SQL seed and the DBC patch JSON files from the live world DB.

### What it does

1. Reads `mod_kill_collector_continent_maps` to learn which `map_id`s belong to which continent.
2. For each `(continent_id, creature_type)` pair in `{1,2,3,4,5,6,7,9,10}`, runs:
   ```sql
   SELECT COUNT(DISTINCT ct.entry)
   FROM creature_template ct
   JOIN creature c ON c.id1 = ct.entry
   JOIN mod_kill_collector_continent_maps m ON m.map_id = c.map
   WHERE ct.type = ? AND m.continent_id = ?
   ```
3. Writes:
   - `data/sql/db-world/updates/mod_kill_collector_totals_seed.sql` - INSERTs into `mod_kill_collector_totals` with auto-assigned `achievement_id` values.
   - `data/dbc/Achievement.dbc.patch.json` - one row per non-empty bucket.
   - `data/dbc/Achievement_Criteria.dbc.patch.json` - dummy criterion (type 68 SCRIPT_EVENT) per achievement.

### Achievement ID layout

With default flags `--achievement-base 30000 --criteria-base 60000`:

| continent_id | name | slot | achievement_id range |
| ---: | --- | ---: | ---: |
| 0   | Eastern Kingdoms | 0 | 30001..30010 |
| 1   | Kalimdor         | 1 | 30011..30020 |
| 530 | Outland          | 2 | 30021..30030 |
| 571 | Northrend        | 3 | 30031..30040 |

`achievement_id = base + slot * 10 + creature_type`. The same offset scheme applies to `criteria_id`.

### Usage

```bash
pip install mysql-connector-python

python3 tools/generate_kill_collector_data.py \
    --host 127.0.0.1 --port 3306 \
    --user acore --password acore \
    --database acore_world
```

Flags:

| Flag | Default | Purpose |
| --- | --- | --- |
| `--host`, `--port`, `--user`, `--password`, `--database` | `127.0.0.1`, `3306`, `acore`, `acore`, `acore_world` | World-DB connection. |
| `--achievement-base` | `30000` | Base for generated achievement IDs. |
| `--criteria-base`    | `60000` | Base for generated criteria IDs. |
| `--category-id`      | `9000`  | Category id written into Achievement.dbc rows. |
| `--out-sql` | `data/sql/db-world/updates/mod_kill_collector_totals_seed.sql` | SQL output path. |
| `--out-ach` | `data/dbc/Achievement.dbc.patch.json` | Achievement DBC patch path. |
| `--out-cri` | `data/dbc/Achievement_Criteria.dbc.patch.json` | Criteria DBC patch path. |
| `--include-empty` | off | Emit rows even when no creatures match (useful for sanity checks). |

### Workflow after running

1. Apply the generated SQL to the world DB:
   ```bash
   mysql -u acore -p acore_world < data/sql/db-world/updates/mod_kill_collector_totals_seed.sql
   ```
2. Patch the stock DBCs (from `share-public/dbc/`) with the generated JSON files using `share-public/python_scripts/patch_dbc.py`.
3. Copy the patched DBCs into `azerothcore-wotlk/data/dbc/`.
4. Pack the patched DBCs into a `patch-K.MPQ` for client distribution.
5. Restart the worldserver. The cache reload picks up the new totals automatically.

### Re-running

Re-run the script whenever:

- New creatures are added to the world DB.
- `mod_kill_collector_continent_maps` changes (new dungeon, new continent).
- The CreatureType list changes.

The SQL output is idempotent (`DELETE FROM mod_kill_collector_totals` followed by `INSERT`), and the DBC JSONs are full snapshots, so old entries are not retained. After re-running, redistribute the patched MPQ to clients.
