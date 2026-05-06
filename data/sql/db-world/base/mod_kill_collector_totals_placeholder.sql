-- =====================================================================
-- mod-kill-collector: PLACEHOLDER bucket totals seed
-- =====================================================================
-- This file is a PLACEHOLDER. Every expected_total is set to 999999,
-- a sentinel value that prevents achievements from completing under
-- this seed (since no continent has 999999 distinct creature entries
-- of any one type).
--
-- REPLACE this placeholder by running the generator against your
-- live world DB:
--
--     python3 tools/generate_kill_collector_data.py \
--         --user acore --password acore --database acore_world
--
-- The generator writes a real seed to
--     data/sql/db-world/updates/mod_kill_collector_totals_seed.sql
-- which DELETEs and re-INSERTs this table with the actual
-- per-bucket counts for your creature DB. Apply it with
--     mysql -u acore -p acore_world < <generated file>
--
-- The achievement_id values below already match what the generator
-- writes (30000 + continent_slot * 10 + creature_type), so you can
-- ship the patched DBCs first and replace the totals later without
-- breaking the achievement-id mapping.
--
-- The C++ KillCollectorMgr emits a LOG_WARN at startup as long as
-- any bucket still has expected_total >= 999999 - check your
-- worldserver log to confirm the placeholder is gone after running
-- the generator.
-- =====================================================================

DELETE FROM `mod_kill_collector_totals`;
INSERT INTO `mod_kill_collector_totals`
    (`continent_id`, `creature_type`, `expected_total`, `achievement_id`) VALUES
    -- Eastern Kingdoms (continent_id=0, slot=0)
    (0,   1, 999999, 30001),  -- Beast
    (0,   2, 999999, 30002),  -- Dragonkin
    (0,   3, 999999, 30003),  -- Demon
    (0,   4, 999999, 30004),  -- Elemental
    (0,   5, 999999, 30005),  -- Giant
    (0,   6, 999999, 30006),  -- Undead
    (0,   7, 999999, 30007),  -- Humanoid
    (0,   9, 999999, 30009),  -- Mechanical
    (0,  10, 999999, 30010),  -- Other / Misc
    -- Kalimdor (continent_id=1, slot=1)
    (1,   1, 999999, 30011),  -- Beast
    (1,   2, 999999, 30012),  -- Dragonkin
    (1,   3, 999999, 30013),  -- Demon
    (1,   4, 999999, 30014),  -- Elemental
    (1,   5, 999999, 30015),  -- Giant
    (1,   6, 999999, 30016),  -- Undead
    (1,   7, 999999, 30017),  -- Humanoid
    (1,   9, 999999, 30019),  -- Mechanical
    (1,  10, 999999, 30020),  -- Other / Misc
    -- Outland (continent_id=530, slot=2)
    (530, 1, 999999, 30021),  -- Beast
    (530, 2, 999999, 30022),  -- Dragonkin
    (530, 3, 999999, 30023),  -- Demon
    (530, 4, 999999, 30024),  -- Elemental
    (530, 5, 999999, 30025),  -- Giant
    (530, 6, 999999, 30026),  -- Undead
    (530, 7, 999999, 30027),  -- Humanoid
    (530, 9, 999999, 30029),  -- Mechanical
    (530,10, 999999, 30030),  -- Other / Misc
    -- Northrend (continent_id=571, slot=3)
    (571, 1, 999999, 30031),  -- Beast
    (571, 2, 999999, 30032),  -- Dragonkin
    (571, 3, 999999, 30033),  -- Demon
    (571, 4, 999999, 30034),  -- Elemental
    (571, 5, 999999, 30035),  -- Giant
    (571, 6, 999999, 30036),  -- Undead
    (571, 7, 999999, 30037),  -- Humanoid
    (571, 9, 999999, 30039),  -- Mechanical
    (571,10, 999999, 30040);  -- Other / Misc
