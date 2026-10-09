# Functions

## Lifecycle

| When | What |
|---|---|
| config load (`OnAfterConfigLoad`) | `LoadConfig()` reads `KillCollector.*`; on a reload (`.reload config`) also `LoadData()` |
| startup (`OnStartup`) | `LoadData()` - after the DBC stores and the world database are loaded |
| login | `LoadState()`: the character's kills (`SELECT entry ... WHERE guid`), its team, the progress per bucket; with achievements on, grants every bucket that is already complete |
| logout | drops the online state |
| character deleted | `DELETE` of its kills inside the deletion transaction |

## LoadData

1. Reads `mod_kill_collector_continent_maps` (overrides) and `mod_kill_collector_achievements` (buckets;
   their continents are the tracked continents).
2. Reads every spawn once: `creature` x `creature_template`, without spawns that only exist during a game
   event (`game_event_creature`) or outside phase 1.
3. Per spawn: continent = override, else the map itself if it is a tracked continent, else its entrance map
   (`MapEntry::entrance_map`) if that is one; battleground and arena maps never count. The bucket must exist.
   Skipped: `UNIT_FLAG_NON_ATTACKABLE | IMMUNE_TO_PC | NOT_SELECTABLE`, `CREATURE_FLAG_EXTRA_TRIGGER`,
   any `npcflag` (unless `Expected.SkipNpcFlagCreatures = 0`), a faction template that does not exist.
4. Per team (Alliance = player faction template 1, Horde = 2): the entry joins the bucket when its faction
   template is not friendly to the team's (`FactionTemplateEntry::IsFriendlyTo`).
5. Builds per team `expectedSize[bucket]` and `bucketsByEntry[entry]` (an entry spawned on two continents
   is in both), logs one line per continent and team, swaps the data in under the lock and recomputes the
   online players' progress.

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
   skipped when already earned or missing from `sAchievementStore`).

## Commands

| Command | Security | What |
|---|---|---|
| `.killcollector status` | player | "Kill Collector: <n> different creatures killed." and per continent "<name>: <killed> of <expected> creatures, <done> of <total> achievements." (buckets with nothing to collect are left out) |
| `.killcollector reload` | administrator, console | `LoadData()` |
| `.killcollector reset [name]` | administrator | the named or selected online player, else the invoker: deletes its kills, empties its collection; earned achievements stay |

## Thread safety

Kills arrive from map threads, logins and commands from other threads: `_online` and the data pointer are
only touched under `_lock`; database writes, items, mail, chat and achievements happen after the lock is
released. The data is immutable once loaded and replaced as a whole.
