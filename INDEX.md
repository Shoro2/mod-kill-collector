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
- [tests/kill_collector_shop_buffs.tbs](tests/kill_collector_shop_buffs.tbs) - bot scenario: the shop's class buffs as spells of their own (+50%, 1 hour, 10 tokens): exact amounts, renewal, one blessing per caster, a normal cast refused (result 9), the copy replacing a normal buff, an area shout, a same-effect case
- [tools/gen_shop_buffs.py](tools/gen_shop_buffs.py) - generator of the shop's buff spells: the Lua rows (fl-lua-scripts `TokenShop_Server.lua`), the server SQL, the client recipe and the sticky ids, from the server's and the client's spell data
- [data/sql/db-world/base/mod_kill_collector_shop_buffs.sql](data/sql/db-world/base/mod_kill_collector_shop_buffs.sql) - GENERATED: `spell_dbc` 2032000-2032067 (the 68 buff copies), `spell_group` / `spell_group_stack_rules` (their stacking)
- [tools/shop_buff_spells.json](tools/shop_buff_spells.json), [tools/shop_buff_ids.json](tools/shop_buff_ids.json) - GENERATED: the client rows' recipe (fl-pipeline `214_token_shop_buff_spells.py`) and the sticky copy ids
- [tests/kill_collector_edges.tbs](tests/kill_collector_edges.tbs) - bot scenario: relog, reload, full bags
