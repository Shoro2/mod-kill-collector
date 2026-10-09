-- mod-kill-collector: characters DB
--
-- mod_kill_collector_kills: one row per (character, creature entry) the character has collected. The
-- achievement progress is computed from these rows at login, so it never drifts from them.
-- A deleted character's rows go with it (PlayerScript::OnPlayerDeleteFromDB).

CREATE TABLE IF NOT EXISTS `mod_kill_collector_kills` (
    `guid`            INT UNSIGNED NOT NULL COMMENT 'characters.guid',
    `entry`           INT UNSIGNED NOT NULL COMMENT 'creature_template.entry',
    `map_id`          INT UNSIGNED NOT NULL COMMENT 'map of the first kill',
    `creature_type`   TINYINT UNSIGNED NOT NULL,
    `first_kill_time` INT UNSIGNED NOT NULL,
    PRIMARY KEY (`guid`, `entry`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
