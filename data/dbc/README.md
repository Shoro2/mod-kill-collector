# DBC patches for mod-kill-collector

This module needs a small set of custom achievement entries patched into the WoW 3.3.5 client and into the AzerothCore server's `data/dbc/` directory.

## Files

| File | Purpose |
| --- | --- |
| `Achievement.dbc.patch.json` | Adds ~36 achievement rows (one per `(continent, creatureType)` pair). Default ID range: `30000-30999`. Default category: `9000`. |
| `Achievement_Criteria.dbc.patch.json` | Adds one criterion row per achievement. Default ID range: `60000-60999`. Uses `type=68` (`SCRIPT_EVENT`) as a dummy criterion - actual completion is triggered server-side via `AchievementMgr::CompletedAchievement`. |

## Workflow

1. Use `share-public/python_scripts/patch_dbc.py` (already part of the toolchain) to inject the JSON-defined rows into the **stock** `Achievement.dbc` and `Achievement_Criteria.dbc` (located in `share-public/dbc/`).
2. Copy the resulting patched DBCs into `azerothcore-wotlk/data/dbc/` on the server. The worldserver picks them up at startup (see `DBCStores.cpp`).
3. Pack the patched DBCs into a custom MPQ patch (e.g. `patch-K.MPQ`) using `MPQEditor` or `mpqarchive`. The patch must contain `DBFilesClient/Achievement.dbc` and `DBFilesClient/Achievement_Criteria.dbc`.
4. Distribute `patch-K.MPQ` to your players. They drop it in `WoW/Data/`. Without it, the achievement panel will not display the new entries, but the server will still award tokens and grant the underlying achievement state.

## Achievement-completion strategy

The stock criterion type 78 (`KILL_CREATURE_TYPE`) does not match "kill all unique entries of type X on map Y" - it counts global kills regardless of map. Rather than fight the criterion engine, this module defines a single dummy criterion per achievement (type 68, `SCRIPT_EVENT`) and triggers the achievement directly from `KillCollectorMgr::TryCompleteAchievement` once the in-memory progress for the bucket reaches the configured `expected_total`. This is the same approach used by other community modules (e.g. mod-individual-progression) for non-stock unlock conditions.

## Localisation

For the first cut, the same English string is written into all 16 locale name fields. A future `mod_kill_collector_l10n.sql` can override the German strings via the standard `*_locale` tables once translations are written.

## ID assignments (default)

| continent_id | creature_type | achievement_id |
| --- | --- | --- |
| 0 (Eastern Kingdoms) | 1..10 | 30000..30009 |
| 1 (Kalimdor) | 1..10 | 30010..30019 |
| 530 (Outland) | 1..10 | 30020..30029 |
| 571 (Northrend) | 1..10 | 30030..30039 |

IDs are also stored in `mod_kill_collector_totals.achievement_id`, so admins can override them per row without touching the DBC patches.
