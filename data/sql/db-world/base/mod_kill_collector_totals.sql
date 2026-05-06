-- mod-kill-collector: continent grouping + per-bucket totals
--
-- mod_kill_collector_continent_maps:
--     Maps any map_id to a logical continent_id. Open-world maps
--     map to themselves; dungeon/raid map_ids fold into the
--     parent continent so instance kills count toward that
--     continent's achievements.
--
-- mod_kill_collector_totals:
--     For each (continent_id, creature_type) pair, defines the
--     total number of distinct creature_template entries that
--     must be killed and the achievement_id to grant on
--     completion. This table is auto-populated by
--     tools/generate_kill_collector_data.py - do not seed it by
--     hand.

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

-- Full seed: open-world maps plus every WotLK dungeon and raid
-- grouped under its parent continent.
--   0   = Eastern Kingdoms
--   1   = Kalimdor
--   530 = Outland
--   571 = Northrend
DELETE FROM `mod_kill_collector_continent_maps`
    WHERE `continent_id` IN (0, 1, 530, 571);
INSERT INTO `mod_kill_collector_continent_maps`
    (`continent_id`, `map_id`) VALUES
    -- Eastern Kingdoms
    (0,   0),    -- open world
    (0,  33),   -- Shadowfang Keep
    (0,  34),   -- The Stockades
    (0,  36),   -- The Deadmines
    (0,  70),   -- Uldaman
    (0,  90),   -- Gnomeregan
    (0, 109),   -- The Sunken Temple (Temple of Atal'Hakkar)
    (0, 189),   -- Scarlet Monastery
    (0, 229),   -- Blackrock Spire (LBRS/UBRS)
    (0, 230),   -- Blackrock Depths
    (0, 289),   -- Scholomance
    (0, 309),   -- Zul'Gurub
    (0, 329),   -- Stratholme
    (0, 409),   -- Molten Core
    (0, 469),   -- Blackwing Lair
    (0, 532),   -- Karazhan
    (0, 568),   -- Zul'Aman
    -- Kalimdor
    (1,   1),    -- open world
    (1,  43),   -- Wailing Caverns
    (1,  47),   -- Razorfen Kraul
    (1,  48),   -- Blackfathom Deeps
    (1, 129),   -- Razorfen Downs
    (1, 209),   -- Zul'Farrak
    (1, 249),   -- Onyxia's Lair
    (1, 269),   -- Caverns of Time: The Black Morass
    (1, 349),   -- Maraudon
    (1, 389),   -- Ragefire Chasm
    (1, 509),   -- Ruins of Ahn'Qiraj
    (1, 531),   -- Temple of Ahn'Qiraj
    (1, 560),   -- Caverns of Time: Old Hillsbrad
    -- Outland
    (530, 530),  -- open world
    (530, 540),  -- Hellfire Citadel: The Shattered Halls
    (530, 542),  -- Hellfire Citadel: The Blood Furnace
    (530, 543),  -- Hellfire Citadel: Ramparts
    (530, 544),  -- Magtheridon's Lair
    (530, 545),  -- Coilfang: The Steamvault
    (530, 546),  -- Coilfang: The Underbog
    (530, 547),  -- Coilfang: The Slave Pens
    (530, 548),  -- Coilfang: Serpentshrine Cavern
    (530, 550),  -- Tempest Keep (The Eye)
    (530, 552),  -- Tempest Keep: The Arcatraz
    (530, 553),  -- Tempest Keep: The Botanica
    (530, 554),  -- Tempest Keep: The Mechanar
    (530, 555),  -- Auchindoun: Shadow Labyrinth
    (530, 556),  -- Auchindoun: Sethekk Halls
    (530, 557),  -- Auchindoun: Mana Tombs
    (530, 558),  -- Auchindoun: Auchenai Crypts
    (530, 564),  -- Black Temple
    (530, 565),  -- Gruul's Lair
    (530, 580),  -- Sunwell Plateau
    (530, 585),  -- Magisters' Terrace
    -- Northrend
    (571, 571),  -- open world
    (571, 533),  -- Naxxramas (WotLK)
    (571, 574),  -- Utgarde Keep
    (571, 575),  -- Utgarde Pinnacle
    (571, 576),  -- The Nexus
    (571, 578),  -- The Oculus
    (571, 595),  -- The Culling of Stratholme
    (571, 599),  -- Halls of Stone
    (571, 600),  -- Drak'Tharon Keep
    (571, 601),  -- Azjol-Nerub
    (571, 602),  -- Halls of Lightning
    (571, 603),  -- Ulduar
    (571, 604),  -- Gundrak
    (571, 615),  -- The Obsidian Sanctum
    (571, 616),  -- The Eye of Eternity
    (571, 619),  -- Ahn'kahet: The Old Kingdom
    (571, 624),  -- Vault of Archavon
    (571, 631),  -- Icecrown Citadel
    (571, 632),  -- The Forge of Souls
    (571, 649),  -- Trial of the Crusader
    (571, 650),  -- Trial of the Champion
    (571, 658),  -- Pit of Saron
    (571, 668),  -- Halls of Reflection
    (571, 724);  -- The Ruby Sanctum

-- mod_kill_collector_totals is left empty here. Populate it
-- with tools/generate_kill_collector_data.py once the creature
-- DB and continent_maps are final.
