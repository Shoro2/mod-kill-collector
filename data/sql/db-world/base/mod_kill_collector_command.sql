-- mod-kill-collector: chat commands.

DELETE FROM `command` WHERE `name` IN ('killcollector status', 'killcollector reload', 'killcollector reset');
INSERT INTO `command` (`name`, `security`, `help`) VALUES
('killcollector status', 0, 'Syntax: .killcollector status\r\nShows how many different creatures you have killed and your progress on each continent.'),
('killcollector reload', 3, 'Syntax: .killcollector reload\r\nRebuilds the Kill Collector''s continents and creature lists from the world database.'),
('killcollector reset', 3, 'Syntax: .killcollector reset [$playername]\r\nForgets every creature the named or selected online player has collected. Achievements already earned stay.');
