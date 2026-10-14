# mod-kill-collector - index

- [README.md](README.md) - what it does (rewards included), installation, configuration, schema
- [CLAUDE.md](CLAUDE.md) - purpose, ids, status, next steps
- [data_structure.md](data_structure.md) - files, tables, the damage bonus on the Player, config keys
- [functions.md](functions.md) - hooks, the expected sets, tokens, achievements, the damage bonus, "N3rd", commands
- [log.md](log.md) - change log, newest first
- [todo.md](todo.md) - open work
- [tests/kill_collector_tokens.tbs](tests/kill_collector_tokens.tbs) - bot scenario (mod-fl-testbots)
- [tests/kill_collector_achievement.tbs](tests/kill_collector_achievement.tbs) - bot scenario: a completed list grants its achievement
- [tests/kill_collector_bonus.tbs](tests/kill_collector_bonus.tbs) - bot scenario: the damage bonus in the combat log
- [tests/kill_collector_meta.tbs](tests/kill_collector_meta.tbs) - bot scenario: stacking to +25%, "N3rd" by a kill and at login
- [tests/kill_collector_shop.tbs](tests/kill_collector_shop.tbs) - bot scenario: the token shop (`.tokenshop`: heirlooms, the XP potion, riding)
- [tests/kill_collector_shop_buffs.tbs](tests/kill_collector_shop_buffs.tbs) - bot scenario: the shop's class buffs (+50%, 1 hour, 10 tokens): exact amounts, renewal, area-spell spill, stacking with a normal cast
- [tools/gen_shop_buffs.py](tools/gen_shop_buffs.py) - generator of the shop's buff rows (fl-lua-scripts `TokenShop_Server.lua`) from the server's spell data
- [tests/kill_collector_edges.tbs](tests/kill_collector_edges.tbs) - bot scenario: relog, reload, full bags
