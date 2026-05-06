-- mod-kill-collector: characters DB schema
--
-- mod_kill_collector_kills:    one row per (guid, entry). Drives
--                              "first kill ever" detection.
-- mod_kill_collector_progress: denormalized counter per (guid,
--                              continent_id, creature_type) used
--                              to trigger achievements.

CREATE TABLE IF NOT EXISTS `mod_kill_collector_kills` (
    `guid`            INT UNSIGNED NOT NULL,
    `entry`           INT UNSIGNED NOT NULL,
    `map_id`          INT UNSIGNED NOT NULL,
    `creature_type`   TINYINT UNSIGNED NOT NULL,
    `first_kill_time` INT UNSIGNED NOT NULL,
    PRIMARY KEY (`guid`, `entry`),
    KEY `idx_player_bucket` (`guid`, `map_id`, `creature_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `mod_kill_collector_progress` (
    `guid`           INT UNSIGNED NOT NULL,
    `continent_id`   INT UNSIGNED NOT NULL,
    `creature_type`  TINYINT UNSIGNED NOT NULL,
    `kill_count`     INT UNSIGNED NOT NULL DEFAULT 0,
    `completed_at`   INT UNSIGNED NULL,
    PRIMARY KEY (`guid`, `continent_id`, `creature_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
