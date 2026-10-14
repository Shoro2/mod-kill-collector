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
takes the module's mutex or touches the database; the bonus is only read. No spell is excluded: a spell that
ignores the caster's modifiers (`SPELL_ATTR3_IGNORE_CASTER_MODIFIERS`) is raised too.

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

## Thread safety

Kills arrive from map threads, logins and commands from other threads: `_online` and the data pointer are
only touched under `_lock`; database writes, items, mail, chat and achievements happen after the lock is
released. The data is immutable once loaded and replaced as a whole. The damage hooks run on map threads for
every blow and take no lock: the bonus lives on the Player (`CustomData`), its entry is created and written
by the manager only from the player's own login, kills and commands (the hooks only `Get` it), and the
config values they read are plain integers set at config load.
