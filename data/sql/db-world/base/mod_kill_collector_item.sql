-- mod-kill-collector: token item
--
-- ID 80001 lies in the conventional custom-item range used by
-- AzerothCore community modules.

DELETE FROM `item_template` WHERE `entry` = 80001;
INSERT INTO `item_template`
    (`entry`, `class`, `subclass`, `name`, `displayid`, `Quality`,
     `stackable`, `bonding`, `description`)
VALUES
    (80001, 15, 0, "Hunter's Token", 6122, 4,
     1000, 1,
     'Earned for the first kill of a unique creature.');
