-- mod-kill-collector: the token shop's Potion of Experience.
--
-- The shop (fl-lua-scripts TokenShop/) sells it for Hunter's Tokens. 920201 lies in the module's item band
-- 920200-920209 (share-public vault, docs/World of Warcraft/06-custom-ids.md). It casts CoA's own spell
-- 818046 "Potion of Experience" (+25 % experience from kills and quests for one hour, persists through death;
-- already in the server's Spell.dbc and the client's CoA overlay, nothing to add there). The item has no
-- Item.dbc row, like the Hunter's Token: the client takes name and tooltip from the item query, the icon from
-- the display id (19003 = INV_Potion_26, the icon of spell 818046).

DELETE FROM `item_template` WHERE `entry` = 920201;
INSERT INTO `item_template`
    (`entry`, `class`, `subclass`, `name`, `displayid`, `Quality`,
     `stackable`, `bonding`, `ItemLevel`,
     `spellid_1`, `spelltrigger_1`, `spellcharges_1`,
     `description`)
VALUES
    (920201, 0, 1, 'Potion of Experience', 19003, 1,
     20, 1, 1,
     818046, 0, -1,
     'Increases experience gained from kills and quests by 25% for 1 hour.');
