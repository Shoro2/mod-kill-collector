# Log (newest first)

- 2026-10-14 test: Repeatable runs - the bots' achievements are reset with mod-fl-testbots' `do <bot> resetachievements` (`.reset achievements` is console-only, so the director only got its usage text), and the scenarios wait 6 s after a `.respawn` (the map spawns a corpse's replacement at its next respawn pass, every 5 s)
- 2026-10-14 fix(Core): Spells that ignore the caster's modifiers get no bonus (no double bonus on procs and copies); the bonus tests use the fixed 4000 of spell 37463
- 2026-10-14 docs: Rewards - README, CLAUDE.md, data_structure, functions, todo
- 2026-10-14 test: kill_collector_meta (44 achievements by command stack to +20% / +25%, the 45th by the kills gives "N3rd", a second part has it come with the next login)
- 2026-10-14 test: kill_collector_bonus (the combat log shows 5000 / 5250, another continent, another type) and the status lines in kill_collector_achievement
- 2026-10-14 feat(Core): Every earned achievement pays +5% damage against its creature type; the meta achievement "N3rd" (30051, title 178) for all 45; status lines for both; the client and server rows come from fl-pipeline 209
- 2026-10-10 test: Relog, reload and full bags; every scenario respawns its creatures (runs 592-594)
- 2026-10-10 feat(DB): The achievements' server rows, and a bot scenario that completes a list (run 584)
- 2026-10-10 docs: Record the workbench test (T1, bot run 583) (632b78e)
- 2026-10-10 docs: Say which game-event spawns the lists leave out (2caef62)
- 2026-10-10 feat(Core): Adopt the module for Forgotten Land (item 920200, FL continent, per-team lists, group credit, commands) (f81cf2a)
- 2026-10-09 docs: Add the per-repo doc set (a63564f)
- 2026-05-06 Add 36-bucket placeholder seed (SQL + DBC patches) (051df18)
- 2026-05-06 Seed full continent map list and add data generator (2f55d65)
- 2026-05-06 Add SQL schema, token item, totals tables, DBC patch skeletons (dd5996a)
- 2026-05-06 Add module skeleton: build, config, C++ source (fdfe24b)
- 2026-05-06 Initial commit (38c66d7)
