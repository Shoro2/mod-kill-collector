#!/usr/bin/env python3
"""Generate seed SQL and DBC patch JSON for mod-kill-collector.

Reads from the AzerothCore world DB:
  - mod_kill_collector_continent_maps  (must be populated first)
  - creature_template
  - creature

Writes:
  - data/sql/db-world/updates/mod_kill_collector_totals_seed.sql
  - data/dbc/Achievement.dbc.patch.json
  - data/dbc/Achievement_Criteria.dbc.patch.json

Usage:
    python3 tools/generate_kill_collector_data.py \\
        --host 127.0.0.1 --port 3306 \\
        --user acore --password acore \\
        --database acore_world

Achievement ID layout (default --achievement-base 30000):
    achievement_id = base + (continent_slot * 10) + creature_type
    criteria_id    = base_criteria + (continent_slot * 10) + creature_type

    continent_slot mapping:
        0   (Eastern Kingdoms) -> slot 0  -> achievements 30001..30010
        1   (Kalimdor)         -> slot 1  -> achievements 30011..30020
        530 (Outland)          -> slot 2  -> achievements 30021..30030
        571 (Northrend)        -> slot 3  -> achievements 30031..30040

Tracked CreatureType values (skip Critter=8, Totem=11,
Non-Combat Pet=12, Gas Cloud=13):
    1 Beast, 2 Dragonkin, 3 Demon, 4 Elemental, 5 Giant,
    6 Undead, 7 Humanoid, 9 Mechanical, 10 Misc.
"""

import argparse
import json
import os
import sys

try:
    import mysql.connector  # type: ignore
except ImportError:
    sys.stderr.write(
        "Missing dependency: mysql-connector-python\n"
        "Install with: pip install mysql-connector-python\n"
    )
    sys.exit(1)

CREATURE_TYPES = {
    1:  ("Beasts",       "beast"),
    2:  ("Dragonkin",    "dragonkin"),
    3:  ("Demons",       "demon"),
    4:  ("Elementals",   "elemental"),
    5:  ("Giants",       "giant"),
    6:  ("Undead",       "undead"),
    7:  ("Humanoids",    "humanoid"),
    9:  ("Mechanicals",  "mechanical"),
    10: ("Other",        "creature"),
}

CONTINENT_NAMES = {
    0:   "Eastern Kingdoms",
    1:   "Kalimdor",
    530: "Outland",
    571: "Northrend",
}

# Mapping from continent_id to a stable 0-based slot used for
# achievement-id calculation. New continents added later get the
# next available slot.
CONTINENT_SLOT = {0: 0, 1: 1, 530: 2, 571: 3}


def compute_slot(continent_id: int) -> int:
    if continent_id not in CONTINENT_SLOT:
        # Allocate a new slot deterministically by sorted insertion.
        new_slot = max(CONTINENT_SLOT.values()) + 1
        CONTINENT_SLOT[continent_id] = new_slot
    return CONTINENT_SLOT[continent_id]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--user", default="acore")
    parser.add_argument("--password", default="acore")
    parser.add_argument("--database", default="acore_world")
    parser.add_argument("--achievement-base", type=int, default=30000,
                        help="Base ID for generated achievements (default 30000).")
    parser.add_argument("--criteria-base",    type=int, default=60000,
                        help="Base ID for generated criteria (default 60000).")
    parser.add_argument("--category-id",      type=int, default=9000,
                        help="Achievement_Category.dbc id (default 9000).")
    parser.add_argument("--out-sql",
                        default="data/sql/db-world/updates/mod_kill_collector_totals_seed.sql")
    parser.add_argument("--out-ach",
                        default="data/dbc/Achievement.dbc.patch.json")
    parser.add_argument("--out-cri",
                        default="data/dbc/Achievement_Criteria.dbc.patch.json")
    parser.add_argument("--include-empty", action="store_true",
                        help="Emit rows even when expected_total is 0.")
    args = parser.parse_args()

    conn = mysql.connector.connect(
        host=args.host, port=args.port,
        user=args.user, password=args.password,
        database=args.database,
    )
    cursor = conn.cursor()

    cursor.execute("SELECT DISTINCT continent_id FROM mod_kill_collector_continent_maps ORDER BY continent_id")
    continents = [row[0] for row in cursor.fetchall()]
    if not continents:
        sys.stderr.write(
            "mod_kill_collector_continent_maps is empty. "
            "Apply data/sql/db-world/base/mod_kill_collector_totals.sql first.\n"
        )
        return 1

    totals_rows = []
    achievement_entries = []
    criteria_entries = []

    for continent_id in continents:
        slot = compute_slot(continent_id)
        continent_name = CONTINENT_NAMES.get(continent_id, f"Continent {continent_id}")
        for creature_type, (display_plural, display_singular) in CREATURE_TYPES.items():
            cursor.execute(
                """
                SELECT COUNT(DISTINCT ct.entry)
                FROM creature_template ct
                JOIN creature c ON c.id1 = ct.entry
                JOIN mod_kill_collector_continent_maps m ON m.map_id = c.map
                WHERE ct.type = %s AND m.continent_id = %s
                """,
                (creature_type, continent_id),
            )
            (expected_total,) = cursor.fetchone()
            if expected_total == 0 and not args.include_empty:
                continue

            achievement_id = args.achievement_base + slot * 10 + creature_type
            criteria_id    = args.criteria_base    + slot * 10 + creature_type
            name = f"{continent_name}: {display_plural}"
            description = (
                f"Slay at least one of every {display_singular} "
                f"in {continent_name} (open world and instances)."
            )

            totals_rows.append((continent_id, creature_type, expected_total, achievement_id))
            achievement_entries.append({
                "id": achievement_id,
                "faction": -1,
                "mapId": -1,
                "name_lang": name,
                "description_lang": description,
                "category": args.category_id,
                "points": 10,
                "orderInGroup": 0,
                "flags": 0,
                "iconId": 0,
                "reward_lang": "",
                "minimumCriteria": 1,
                "shares_criteria": 0,
            })
            criteria_entries.append({
                "id": criteria_id,
                "achievement": achievement_id,
                "type": 68,                                    # ACHIEVEMENT_CRITERIA_TYPE_SCRIPT_EVENT
                "asset_id": continent_id * 100 + creature_type,
                "quantity": 1,
                "start_event": 0,
                "start_asset": 0,
                "flags": 0,
                "description_lang": description,
                "completionFlag": 0,
                "groupFlag": 0,
                "timerStartEvent": 0,
                "timer_asset": 0,
                "timer_time": 0,
                "showOrder": 0,
            })

    cursor.close()
    conn.close()

    os.makedirs(os.path.dirname(args.out_sql) or ".", exist_ok=True)
    with open(args.out_sql, "w", encoding="utf-8") as f:
        f.write("-- Auto-generated by tools/generate_kill_collector_data.py.\n")
        f.write("-- Do not edit by hand - re-run the generator instead.\n\n")
        f.write("DELETE FROM `mod_kill_collector_totals`;\n")
        if totals_rows:
            f.write(
                "INSERT INTO `mod_kill_collector_totals` "
                "(`continent_id`, `creature_type`, `expected_total`, `achievement_id`) VALUES\n"
            )
            f.write(",\n".join(
                f"    ({c}, {t}, {n}, {a})" for (c, t, n, a) in totals_rows
            ))
            f.write(";\n")
    print(f"[+] wrote {args.out_sql} ({len(totals_rows)} buckets)")

    os.makedirs(os.path.dirname(args.out_ach) or ".", exist_ok=True)
    with open(args.out_ach, "w", encoding="utf-8") as f:
        json.dump({
            "_comment": (
                "Auto-generated by tools/generate_kill_collector_data.py. "
                "Re-run after creature DB or continent_maps changes."
            ),
            "_columns": [
                "id", "faction", "mapId", "name_lang", "description_lang",
                "category", "points", "orderInGroup", "flags", "iconId",
                "reward_lang", "minimumCriteria", "shares_criteria",
            ],
            "entries": achievement_entries,
        }, f, indent=2)
        f.write("\n")
    print(f"[+] wrote {args.out_ach} ({len(achievement_entries)} achievements)")

    with open(args.out_cri, "w", encoding="utf-8") as f:
        json.dump({
            "_comment": (
                "Auto-generated by tools/generate_kill_collector_data.py. "
                "type=68 (ACHIEVEMENT_CRITERIA_TYPE_SCRIPT_EVENT) is a dummy "
                "criterion - actual completion is triggered server-side via "
                "AchievementMgr::CompletedAchievement."
            ),
            "_columns": [
                "id", "achievement", "type", "asset_id", "quantity",
                "start_event", "start_asset", "flags", "description_lang",
                "completionFlag", "groupFlag", "timerStartEvent",
                "timer_asset", "timer_time", "showOrder",
            ],
            "entries": criteria_entries,
        }, f, indent=2)
        f.write("\n")
    print(f"[+] wrote {args.out_cri} ({len(criteria_entries)} criteria)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
