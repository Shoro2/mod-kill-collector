# Functions

## Lifecycle

| When | What |
|---|---|
| config load (`OnAfterConfigLoad`) | `LoadConfig()` reads `KillCollector.*`; on a reload (`.reload config`) also `LoadData()` |
| startup (`OnStartup`) | `LoadData()` - after the DBC stores and the world database are loaded |
| login | `LoadState()`: the character's kills (`SELECT entry ... WHERE guid`), its team, the progress per bucket; with achievements on, grants every bucket that is already complete, then the meta achievement; then `RecomputeDamageBonus()` (also with achievements off) |
| achievement completed (`OnPlayerAchievementComplete`) | a bucket achievement (also one a game master added): `RecomputeDamageBonus()` |
| logout | drops the online state |
| character deleted | `DELETE` of its kills inside the deletion transaction |

## LoadData

1. Reads `mod_kill_collector_continent_maps` (overrides) and `mod_kill_collector_achievements` (buckets;
   their continents are the tracked continents).
2. Reads every spawn once: `creature` x `creature_template`, without spawns that only exist during a game
   event (`game_event_creature` with a positive `eventEntry`; a negative one only hides the spawn during
   the event) or outside phase 1.
3. Per spawn: continent = override, else the map itself if it is a tracked continent, else its entrance map
   (`MapEntry::entrance_map`) if that is one; battleground and arena maps never count. The bucket must exist.
   Skipped: `UNIT_FLAG_NON_ATTACKABLE | IMMUNE_TO_PC | NOT_SELECTABLE`, `CREATURE_FLAG_EXTRA_TRIGGER`,
   any `npcflag` (unless `Expected.SkipNpcFlagCreatures = 0`), a faction template that does not exist.
4. Per team (Alliance = player faction template 1, Horde = 2): the entry joins the bucket when its faction
   template is not friendly to the team's (`FactionTemplateEntry::IsFriendlyTo`).
5. Builds per team `expectedSize[bucket]` and `bucketsByEntry[entry]` (an entry spawned on two continents
   is in both), logs one line per continent and team and one for the rewards, swaps the data in under the
   lock and recomputes the online players' progress.

## A kill

`OnPlayerRewardKillRewarder` fires for every player the kill rewards (the killer, the group members within
reward distance, the owner of a pet or totem); the victim must be a creature. `OnKillCredit`:

1. Filters: not in GM mode; not a pet, totem or player-charmed creature; not a gas cloud, nor a critter /
   totem / non-combat pet unless configured; not in a battleground or arena; open world / instance
   switches; `MinLevelDelta`.
2. Under the lock: the entry joins the player's collection - nothing more happens if it was there; each
   bucket of the player's team that holds the entry counts one up; a bucket that reaches its size names its
   achievement (achievements on).
3. Outside the lock: `INSERT IGNORE` into `mod_kill_collector_kills`, the tokens (`CanStoreNewItem` /
   `StoreNewItem` / `SendNewItem`, the rest by mail from the player with the GM stationery), the chat line
   "New creature collected: <name> (<n> in total).", the achievements (`Player::CompletedAchievement`,
   skipped when already earned or missing from `sAchievementStore`). When one was granted: the damage bonus
   is recomputed and the meta achievement checked.

## The damage bonus

`KillCollectorUnitScript` (a `UnitScript`) raises damage in three hooks, all through the same test:

| Hook | Damage it sees |
|---|---|
| `ModifyMeleeDamage` | a melee swing (per weapon damage), before armor |
| `ModifySpellDamageTaken` | direct spell damage, before armor, resistance and the critical strike (a crit multiplies the raised value); skipped at 0 |
| `ModifyPeriodicDamageAurasTick` | a damage-over-time tick before its mitigation; the core calls this hook for healing ticks too, so only spells with a periodic damage, percent damage or leech aura count |

The test (`Boost`), cheapest first: the target is a creature (`IsCreature()`) that no player controls
(`!IsControlledByPlayer()`: no bonus against players or their pets); `DamageBonusPct` is not 0 (and the module
is on); the attacker resolves to a player (`GetCharmerOrOwnerPlayerOrPlayerItself()`: the player itself, its
pets, guardians, totems, a creature it controls); that player has a `KillCollectorBonus` on its `CustomData`;
the target's creature type (`GetCreatureType()` = the template's `type`) has earned achievements. Then
`damage = damage * (100 + earned * DamageBonusPct) / 100` in 64-bit, clamped to the damage type. Nothing here
takes the module's mutex or touches the database; the bonus is only read. The two spell hooks leave out the
spells that ignore the caster's modifiers (`SPELL_ATTR3_IGNORE_CASTER_MODIFIERS`, `IgnoresCasterModifiers`), as
the game's own creature-type damage auras do (`Unit::SpellPctDamageModsDone`): mostly procs and copies whose
amount comes from damage that was raised already (Ignite, the CoA classes' copy damage), so no blow gets the
bonus twice.

`RecomputeDamageBonus(player)` rebuilds `earned[type]` from `player->HasAchieved(id)` for every bucket in
`mod_kill_collector_achievements` (the earned achievements are the source of truth, the characters DB keeps
them). Called at login, after a grant, when a bucket achievement completes, and by `.killcollector status`.

## The meta achievement

`GetMetaProgress()` counts, for the player's team, the bucket achievements whose bucket holds at least one
creature (`expectedSize > 0`: today all 45) and how many of them the player has earned.
`GrantMetaAchievement()` (achievements on, not for a game master in GM mode) completes
`KillCollector.MetaAchievementId` (30051) with `Player::CompletedAchievement` when all are earned and the
meta is not; the core's `achievement_reward` row then gives the title ("N3rd %s", CharTitles 178). It runs at
login (so a player that earned everything before the meta existed gets it) and after a bucket achievement was
granted. The decision is made on a copy of the data, the grant outside the lock.

## Commands

| Command | Security | What |
|---|---|---|
| `.killcollector status` | player | "Kill Collector: <n> different creatures killed." and per continent "<name>: <killed> of <expected> creatures, <done> of <total> achievements." (buckets with nothing to collect are left out); rereads the earned achievements, then "Damage bonus: +10% beasts, +5% undead" (or "Damage bonus: none"), and "N3rd: earned" or "N3rd: not yet (<done> of <total> achievements)" |
| `.killcollector reload` | administrator, console | `LoadData()` |
| `.killcollector reset [name]` | administrator | the named or selected online player, else the invoker: deletes its kills, empties its collection; earned achievements (and the bonus) stay |

## The token shop (not in this module's code)

The tokens are spent by fl-lua-scripts `TokenShop/` (Lua, AIO + `.tokenshop`), which counts item 920200 in the bags only
(`Player:GetItemCount`) and removes it with `Player:RemoveItem`. This module contributes the potion item 920201
(`data/sql/db-world/base/mod_kill_collector_shop.sql`: a use spell 818046 with one charge, stack 20, bind on pickup)
and the scenarios `tests/kill_collector_shop.tbs` and `tests/kill_collector_shop_buffs.tbs`. No C++ here changes for the shop.

## The token shop's class buffs: spells of their own (SQL + generator, no C++)

The shop's class buffs (General tab, 68 rows, 10 tokens, +50% for one hour) are spells of their own since 2026-10-15 (the
operator: a normal class buff must not override the shop buff - it fails with "A more powerful spell is already active" -
and the buff tooltip must show the real numbers; a client patch is fine). The shop's Lua only casts the copy
(fl-lua-scripts `functions.md`, section TokenShop); everything below is generated by `tools/gen_shop_buffs.py` and lives in
`data/sql/db-world/base/mod_kill_collector_shop_buffs.sql` (applied by the updater at boot) and, for the client,
`tools/shop_buff_spells.json` (fl-pipeline `214_token_shop_buff_spells.py` writes it into the client's Spell.dbc, hot and
CoA overlay, shipped in patch-9).

- **Ids**: Spell **2032000-2032067** (band 2032000-2032099 of the vault's `06-custom-ids.md`, free in the server file and
  table, hot and the CoA overlay, measured 2026-10-15), sticky in `tools/shop_buff_ids.json` (original spell id -> copy id);
  spell groups **2300000-2300399** (4 per copy id; 74 used).
- **A copy** is the original's top-rank row (Blessing of Sanctuary: 67480, the stat aura its script casts; its damage
  reduction and mana proc are not part of the copy) with: every effect whose aura type is an amount the shop scales
  (`SCALE_AURAS`: stat, resistance, armor, attack power melee and ranged, Ascension spell power 345, mana per 5 s, max
  health, damage shield, percent stats, percent costs) kept at the SAME effect index with its amount x1.5 (round half up, at
  level 80, no random points, no per-level part - Battle Shout 550 -> 825, Man'ari Intuition's armor 290 -> 435) as a plain
  APPLY_AURA on the caster (implicit target 1: a self buff, never an area aura); every other effect dropped (Kings' no-op aura
  166, Mana Module's custom effect 168); DurationIndex 42 = 3,600,000 ms; the cast data cleared (cost, reagents, cooldown,
  category, global cooldown, range = self, stances, aura states, proc mask, targets, rune cost, spell focus); **no spell
  family** (`SpellClassSet` and `SpellClassMask_*` 0, so no talent, glyph or class script keyed to the family or the spell id
  touches it, it has no `SpellSpecific` and belongs to no per-caster blessing group); the `Attributes` bits DO_NOT_DISPLAY (a
  hidden aura would not show on the buff bar) and COOLDOWN_ON_EVENT cleared; the original's name, icon and visuals, the rank
  text "Empowered", and the client's description texts with the statements that no longer hold removed (the shouts' party
  reach, the "only one per caster" sentences).
- **The stacking** is `spell_group` data: the copy joins every EXCLUSIVE_HIGHEST (stack rule 4) group its original sits in
  (18: 1002-1005, 1083-1085, 1088, 1089, 1093, 1098, 1113, 2100002-2100004, 2104883, 2106086, 2106087 - they already hold the
  stock group versions: Prayer of Fortitude, Gift of the Wild, Arcane Brilliance, the Greater Blessings, CoA's Greater X); where
  no such group covers a spell of the original's family - its rank chain's first rank(s) (Brutal Shout's rank 7 is outside its
  chain), its group ("Greater <name>") version, Kings' Greater Blessing 25898 - a group of its own holds that spell's first rank
  and the copy (74 groups, one spell each where two of them have no rule between them today, so that no existing pair changes
  its rule: the proof is a port of `SpellMgr::CheckSpellGroupStackRules` inside the generator). Ranks are not used: the groups
  reach every rank through the chain's first rank. What the core then does (read from `Spell::CheckCast`,
  `Unit::IsHighestExclusiveAuraEffect`, `Unit::_RemoveNoStackAurasDueToAura`, `Aura::CanStackWith`; the scenario measures it):
  1. A normal SINGLE-TARGET cast on a holder of the copy fails in `CheckCast` with SPELL_FAILED_AURA_BOUNCED (9, "A more
     powerful spell is already active") when its amount is lower - nothing changes, no mana is spent.
  2. The copy cast on a holder of the normal buff replaces it (its amounts are higher); the same copy again refreshes itself.
  3. AREA casts (the shouts, Horn of Winter, the Greater / Prayer / Gift versions) are not refused: `CheckCast` skips spells that
     target an area; on the holder the weaker aura is dropped when it is applied (`_AddAura`), the rest of the group get theirs.
  4. A normal buff that talents or glyphs make stronger than the copy still wins (the check compares the amounts it would
     really give: Thorns with Brambles, 73 x 1.75 = 128 against 110).
  5. Copies that share an exclusive-highest group replace each other: Might and Battle Shout (both in "Flat AP Buffs" 1004),
     Man'ari Intuition and Mark of the Wild (1089). Copies of different groups coexist: Kings, Might and Sanctuary together
     (the paladin's per-caster rule is group 1010 and the copies are not in it).
  6. The copies are NOT members of the same-effect groups (1124-1126 Intellect / Spirit / Stamina buffs, 1105 MP5, 1038 "All
     stats %", 2000180-2000185): where the originals would not add up, the copies do (a shop Kings multiplies with a Templar's
     Gift of Fervor, a shop Fortitude adds to a warlock's Blood Pact).
  7. Sanctuary: a normal Blessing of Sanctuary is not refused (its own effect is a dummy aura, the copy has none); the stat aura
     its script casts (67480, 10%) shares the copy's group and is refused (15% is higher).
- **The generator** reads the server's `Data/dbc/Spell.dbc` overlaid with `spell_dbc` (the table wins), `SpellDuration.dbc`,
  `spell_ranks`, `spell_group`, `spell_group_stack_rules` (with its own rows ignored, so it runs again after the SQL is
  applied) and the client's effective Spell.dbc (the CoA overlay: its texts are the clean 3.3.5a ones, the server's CoA rows
  keep Ascension variables). It refuses (exit 1) on: an id taken, a source row that differs between server and client in an
  amount, a text rule that does not match, a tooltip that keeps a variable or names an effect the copy lacks, a group that does
  not end at rule 4 against everything it must exclude. `--verify` regenerates in memory and compares with the files
  (run it against the live database: IDENTICAL x4 proves the committed SQL / recipe / Lua rows match what the live tables
  say); `--list` prints the copy list with the groups, `--tooltips` every copy's rendered tooltip. Environment overrides:
  `FL_WORLD_DB="host;port;user;pw;db"`, `FL_CLIENT_SPELL_DBC`, `FL_DBC_DIR`. Add a buff by adding its id to `PICKS` (class
  heading, spell id, shop name[, `{"source": id}` when the real aura is another spell, `{"greater": [ids]}` for a stock group
  version no group covers]), run it with `--insert` / `--sql` / `--spec`, commit the four files; the new copy takes the next
  free id of the band.
- **Tests**: `tests/kill_collector_shop_buffs.tbs` (mage, priest, warrior, bloodmage, paladin): amounts through `.list auras id
  <copy>`, the refusals through `do <bot> clientcast <spell> on <unit>` (its output holds `cast failed: spell <id>, result 9`),
  the replacements, and - as predictions to confirm - the area shout and Sanctuary's script aura.

## Thread safety

Kills arrive from map threads, logins and commands from other threads: `_online` and the data pointer are
only touched under `_lock`; database writes, items, mail, chat and achievements happen after the lock is
released. The data is immutable once loaded and replaced as a whole. The damage hooks run on map threads for
every blow and take no lock: the bonus lives on the Player (`CustomData`), its entry is created and written
by the manager only from the player's own login, kills and commands (the hooks only `Get` it), and the
config values they read are plain integers set at config load.
