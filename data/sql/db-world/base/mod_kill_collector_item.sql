-- mod-kill-collector: the token a first kill pays.
--
-- 920200 lies in Forgotten Land's custom item band; 920200-920209 belong to this module
-- (share-public vault, docs/World of Warcraft/06-custom-ids.md).

DELETE FROM `item_template` WHERE `entry` = 920200;
INSERT INTO `item_template`
    (`entry`, `class`, `subclass`, `name`, `displayid`, `Quality`,
     `stackable`, `bonding`, `description`)
VALUES
    (920200, 15, 0, 'Hunter''s Token', 6122, 4,
     1000, 1,
     'Earned for the first kill of a creature you have never killed before.');
