-- mod-kill-collector: continent grouping + per-bucket totals
--
-- mod_kill_collector_continent_maps:
--     Maps any map_id to a logical continent_id. To include a
--     dungeon or raid in a continent's achievement scope, add a
--     row mapping its map_id to the parent continent_id.
--
-- mod_kill_collector_totals:
--     For each (continent_id, creature_type) pair, defines the
--     total number of distinct creature_template entries that
--     must be killed and the achievement_id to grant on
--     completion. expected_total can be auto-computed by an admin
--     script (DISTINCT entry count from creature_template JOIN
--     creature JOIN continent_maps).

CREATE TABLE IF NOT EXISTS `mod_kill_collector_continent_maps` (
    `continent_id` INT UNSIGNED NOT NULL,
    `map_id`       INT UNSIGNED NOT NULL,
    PRIMARY KEY (`continent_id`, `map_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `mod_kill_collector_totals` (
    `continent_id`   INT UNSIGNED NOT NULL,
    `creature_type`  TINYINT UNSIGNED NOT NULL,
    `expected_total` INT UNSIGNED NOT NULL,
    `achievement_id` INT UNSIGNED NOT NULL,
    PRIMARY KEY (`continent_id`, `creature_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Seed: the four main continents (open world only).
-- Add dungeon/raid map_ids in a follow-up migration.
DELETE FROM `mod_kill_collector_continent_maps`
    WHERE `continent_id` IN (0, 1, 530, 571);
INSERT INTO `mod_kill_collector_continent_maps`
    (`continent_id`, `map_id`) VALUES
    (0,   0),     -- Eastern Kingdoms
    (1,   1),     -- Kalimdor
    (530, 530),   -- Outland
    (571, 571);   -- Northrend

-- mod_kill_collector_totals is left empty in the seed; populate
-- it via an admin script once the creature DB is finalized and
-- the matching DBC achievement IDs are known.
