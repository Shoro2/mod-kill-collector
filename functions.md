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
and the buff tooltip must show the real numbers; a client patch is fine; the follow-up: a copy follows every stacking rule
its original follows). The shop's Lua only casts the copy (fl-lua-scripts `functions.md`, section TokenShop); everything below
is generated by `tools/gen_shop_buffs.py` and lives in `data/sql/db-world/base/mod_kill_collector_shop_buffs.sql` (applied by
the updater at boot) and, for the client, `tools/shop_buff_spells.json` (fl-pipeline `214_token_shop_buff_spells.py` writes
it into the client's Spell.dbc, hot and CoA overlay, shipped in patch-9).

- **Ids**: Spell **2032000-2032067** (band 2032000-2032099 of the vault's `06-custom-ids.md`, free in the server file and
  table, hot and the CoA overlay, measured 2026-10-15), sticky in `tools/shop_buff_ids.json` (original spell id -> copy id);
  spell groups **2300000-2300399** (4 per copy id; the 82 pair groups use 2300012-2300269).
- **A copy** is the original's top-rank row (Blessing of Sanctuary: 67480, the stat aura its script casts, plus the damage
  reduction 68066 its generic script casts as the copy's THIRD effect: aura 87 on all schools, -3% x1.5 = **-5%**; its mana
  proc 57319 is not part of the copy) with: every effect whose aura type is an amount the shop scales (`SCALE_AURAS`: stat,
  resistance, armor, attack power melee and ranged, Ascension spell power 345, mana per 5 s, max health, damage shield,
  percent stats, percent costs, damage taken percent) kept at the SAME effect index with its amount x1.5 (round half up on the
  MAGNITUDE, at level 80, no random points, no per-level part - Battle Shout 550 -> 825, Man'ari Intuition's armor 290 -> 435,
  a reduction -3% -> -5%, Mark of Zeliek's and Devotion of Grace's costs -5% -> -8%) as a plain APPLY_AURA on the caster
  (implicit target 1: a self buff, never an area aura); every other effect dropped (Kings' no-op aura 166, Mana Module's
  custom effect 168); DurationIndex 42 = 3,600,000 ms; the cast data cleared (cost, reagents, cooldown, category, global
  cooldown, range = self, stances, aura states, proc mask, targets, rune cost, spell focus); **no spell family**
  (`SpellClassSet` and `SpellClassMask_*` 0, so no talent, glyph or class script keyed to the family or the spell id touches
  it and it has no `SpellSpecific`); the `Attributes` bits DO_NOT_DISPLAY (a hidden aura would not show on the buff bar) and
  COOLDOWN_ON_EVENT cleared; the original's name, icon and visuals, the rank text "Empowered", and the client's description
  texts with the statements that no longer hold removed (the shouts' party reach, the "only one per caster" sentences).
- **The stacking** is `spell_group` data, generated and proven by a port of `SpellMgr::CheckSpellGroupStackRules` (the core takes
  the FIRST non-zero rule of the groups two spells share, lowest group id first, and skips a group when a group nested in it holds
  both spells). A copy has the relations its original has, plus the exclusion of the normal versions of itself:
  1. **It joins the groups of its original.** Every group of the original that carries a rule: EXCLUSIVE 1006 (Kings variants),
     2100001 (the Reaper's Rites); per caster 1010 (Blessings), 1011 (Warrior Shouts), 1135, 1136, 1138, 1139, 1140, 1160, 1171,
     1210, 103955 (the CoA families: one Wisdom, one Module, one Pheromone, one Edict, one Etching, one Gift, one Call, one
     Barbarian shout, one Instinct per caster); same effect 1038 (all stats percent, with Sanctuary) and 2000185 (damage taken
     percent); EXCLUSIVE_HIGHEST 1002, 1003, 1005, 1083-1085, 1088, 1093, 1098, 1113, 2100002-2100004, 2104883, 2106086, 2106087;
     and the rule-less group 1078, an exception nested in 1089 (Man'ari Intuition, Greater Man'ari and Mark of the Wild do not
     exclude each other; so neither do their copies). A group the copy reaches through a nested group it joins gets no row of
     its own (1010, 1038 and 1004 follow from 1006, 1002 and 1003; 1124-1126 from 1085, 1083 and 1084). A group where nothing but
     the copy's own normal versions sits is not joined (a pair group does the same). A same-effect group is joined only where
     the aura type the core guesses for it (the most frequent aura type of its members, read from the loader) is one of the
     copy's - else the core logs an error at boot; the generator proves that no copy changes the guess. The raid groups
     2000180-2000184 hold none of the originals (and the core counts only area aura effects in them): no copy is in them.
  2. **Rule 4 with the normal versions of the same spell**: the rank chain's first ranks and the spells that carry the same
     aura (68066 for Sanctuary), and with a group ("Greater ...") version whose relation to the original REPLACES (rule 1, 2 or 4:
     the newer cast wins) - so a normal cast never overrides the copy. A Greater version the original may stack with (rule 0 or 3:
     Greater Man'ari Intuition, many CoA raid versions) stays stackable: the shop never takes away what the original gives.
     A normal spell the original does nothing with (Blessing of Sanctuary's dummy 20911 and the Greater 25899, which only run
     scripts) gets **no rule** with the copy: a rule 4 there would let the dummy remove the copy.
  3. **82 pair groups** (2300012-2300269; 80 with rule 4, 2 without a rule): one per spell the copy must end at rule 4 (or 0)
     with where no group already makes it so - the copy and that spell. 47 of them are also **nested** in the older groups that
     would come first (a `spell_group` row with a negative spell id, 48 rows in 15 groups: 1006, 1010, 1011, 1038, 1135, 1136,
     1138, 1139, 1140, 1160, 1171, 1210, 103955, 2000185, 2100001): without that an EXCLUSIVE or per-caster group (lower id)
     would be the first the core finds for the pair and the bounce would never happen.
  What the core then does (read from `Spell::CheckCast`, `Unit::IsHighestExclusiveAuraEffect`, `Unit::_RemoveNoStackAurasDueToAura`,
  `Aura::CanStackWith`, `Unit::GetHighestExclusiveSameEffectSpellGroupValue`; the scenario measures it):
  1. A normal SINGLE-TARGET cast on a holder of the copy fails in `CheckCast` with SPELL_FAILED_AURA_BOUNCED (9, "A more
     powerful spell is already active") when its amount is lower - nothing changes, no mana is spent.
  2. The copy cast on a holder of the normal buff replaces it (its amounts are higher); the same copy again refreshes itself.
  3. AREA casts (the shouts, Horn of Winter, the Greater / Prayer / Gift versions) are not refused: `CheckCast` skips spells that
     target an area; on the holder the weaker aura is dropped when it is applied (`_AddAura`), the rest of the group get theirs.
  4. A normal buff that talents or glyphs make stronger than the copy still wins (the check compares the amounts it would
     really give: Thorns with Brambles, 73 x 1.75 = 128 against 110).
  5. **Per caster, as the originals**: the buyer is the caster of every copy, so of one family with a per-caster rule the
     newest copy replaces the older one (Kings, Might, Wisdom and Sanctuary: one blessing; Battle Shout and Commanding Shout:
     one shout; the class's Edicts, Etchings, Pheromones, Modules, Calls, Instincts ...); the shop's answer names what it
     replaced (fl-lua-scripts). Another player's blessing (another caster) coexists, as with the originals. A rule-1 family
     (the Rites; Kings variants) is one at a time for every caster. Copies of different families coexist unless a rule-4 group
     joins them (Might and Battle Shout copies share the flat attack power group 1004: the higher one stays).
  6. **Same effect, as the originals**: the copies sit in the same-effect groups of their originals, so only the highest amount of
     the group counts: a shop Fortitude (248 stamina) and K'iru's Song of Victory (79, group 1126 but not the exclusive-highest
     part) do not add. A spell the original has no rule with (a Templar's Gift of Fervor and Kings share no group; Blood Pact shares
     none with Power Word: Fortitude) adds to the copy exactly as it adds to the original.
  7. **Sanctuary**: a normal Blessing of Sanctuary on a holder is not refused or removed (rule 0 with the copy); the two auras its
     scripts cast, the stats 67480 (10%) and the damage reduction 68066 (-3%), are turned away as weaker than the copy's 15% and
     -5%. The copy's damage reduction is in the same-effect group 2000185 (damage taken) and its stats in 1038. The normal
     blessing's own mana proc (57319) still works, the copy has none.
- **The generator** reads the server's `Data/dbc/Spell.dbc` overlaid with `spell_dbc` (the table wins), `SpellDuration.dbc`,
  `spell_ranks`, `spell_group`, `spell_group_stack_rules` (with its own rows ignored - the copies, the band's groups and the band's
  groups nested in older ones - so it runs again after the SQL is applied) and the client's effective Spell.dbc (the CoA overlay: its
  texts are the clean 3.3.5a ones, the server's CoA rows keep Ascension variables). It refuses (exit 1) on: an id taken, a source row
  that differs between server and client in an amount, a text rule that does not match, a tooltip that keeps a variable or names an
  effect the copy lacks, a donor effect the client row does not hold, and any pair of the stacking proof that ends at another rule
  than planned (copy / each normal version, copy / every spell its original has a rule with, copy / copy, no pair of normal spells
  changed, no same-effect group changing its guessed aura type). `--verify` regenerates in memory and compares with the files
  (run it against the live database: IDENTICAL x4 proves the committed SQL / recipe / Lua rows match what the live tables say),
  `--installed` (read-only) compares the generated rows with what the live tables hold (spell_dbc, spell_group,
  spell_group_stack_rules: all rows of the band, nested ones included), `--list` prints the copy list with the groups, `--tooltips`
  every copy's rendered tooltip. Environment overrides: `FL_WORLD_DB="host;port;user;pw;db"`, `FL_CLIENT_SPELL_DBC`, `FL_DBC_DIR`.
  Add a buff by adding its id to `PICKS` (class heading, spell id, shop name[, options]: `source` when the real aura is another
  spell, `greater` for a stock group version no group covers, `add` = [(spell, effect index)] for an effect taken from another
  spell, `exclude` for further spells with the same aura, `inert` for spells that only run scripts), run it with `--insert` / `--sql`
  / `--spec`, commit the four files; the new copy takes the next free id of the band.
- **Tests**: `tests/kill_collector_shop_buffs.tbs` (slots 1-8: mage, priest, warrior, bloodmage, paladin and three mage twins):
  amounts through `.list auras id <copy>`, the refusals through `do <bot> clientcast <spell> on <unit>` (its output holds `cast
  failed: spell <id>, result 9`), the replacements, the per-caster rule of the blessings (the shop's answer names the replaced
  buff), the same-effect rule through max health (`maxhealth` of mage twins: copy only against copy + K'iru's Song of Victory) and
  - as predictions to confirm - the area shout and Sanctuary's two script auras.

## Thread safety

Kills arrive from map threads, logins and commands from other threads: `_online` and the data pointer are
only touched under `_lock`; database writes, items, mail, chat and achievements happen after the lock is
released. The data is immutable once loaded and replaced as a whole. The damage hooks run on map threads for
every blow and take no lock: the bonus lives on the Player (`CustomData`), its entry is created and written
by the manager only from the player's own login, kills and commands (the hooks only `Get` it), and the
config values they read are plain integers set at config load.
