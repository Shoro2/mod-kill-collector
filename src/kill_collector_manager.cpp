#include "kill_collector_manager.h"

#include "Chat.h"
#include "Config.h"
#include "Creature.h"
#include "CreatureData.h"
#include "DBCStores.h"
#include "DatabaseEnv.h"
#include "Item.h"
#include "Log.h"
#include "Mail.h"
#include "Map.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "SharedDefines.h"
#include "UnitDefines.h"
#include "World.h"

#include <algorithm>
#include <map>

using namespace KillCollector;

KillCollectorMgr* KillCollectorMgr::instance()
{
    static KillCollectorMgr inst;
    return &inst;
}

void KillCollectorMgr::LoadConfig()
{
    _enabled              = sConfigMgr->GetOption<bool>("KillCollector.Enable", false);
    _tokenItemId          = sConfigMgr->GetOption<uint32>("KillCollector.TokenItemId", DEFAULT_TOKEN_ITEM_ID);
    _tokensPerKill        = sConfigMgr->GetOption<uint32>("KillCollector.TokensPerFirstKill", 1);
    _announceFirstKill    = sConfigMgr->GetOption<bool>("KillCollector.AnnounceFirstKill", true);

    _includeOpenWorld     = sConfigMgr->GetOption<bool>("KillCollector.IncludeOpenWorld", true);
    _includeInstances     = sConfigMgr->GetOption<bool>("KillCollector.IncludeInstances", true);
    _includeCritters      = sConfigMgr->GetOption<bool>("KillCollector.IncludeCritters", false);
    _includeTotems        = sConfigMgr->GetOption<bool>("KillCollector.IncludeTotems", false);
    _includeNonCombatPets = sConfigMgr->GetOption<bool>("KillCollector.IncludeNonCombatPets", false);
    _minLevelDelta        = sConfigMgr->GetOption<int32>("KillCollector.MinLevelDelta", -100);

    _skipNpcFlagCreatures = sConfigMgr->GetOption<bool>("KillCollector.Expected.SkipNpcFlagCreatures", true);
    _achievementsEnable   = sConfigMgr->GetOption<bool>("KillCollector.AchievementsEnable", false);
    _damageBonusPct       = std::min<uint32>(sConfigMgr->GetOption<uint32>("KillCollector.DamageBonusPct", DEFAULT_DAMAGE_BONUS_PCT), 100);
    _metaAchievementId    = sConfigMgr->GetOption<uint32>("KillCollector.MetaAchievementId", META_ACHIEVEMENT_ID);
    _logVerbose           = sConfigMgr->GetOption<bool>("KillCollector.LogVerbose", false);
}

int32 KillCollectorMgr::ResolveContinent(Data const& data, uint32 mapId)
{
    // 1. An explicit row: Forgotten Land's own maps, and the maps whose creatures never count.
    auto itOverride = data.continentByMap.find(mapId);
    if (itOverride != data.continentByMap.end())
        return itOverride->second;

    // 2. A tracked continent itself.
    if (data.continents.count(mapId))
        return int32(mapId);

    // 3. A dungeon or raid: the continent its entrance is on (Map.dbc / map_dbc). Battlegrounds never count.
    MapEntry const* map = sMapStore.LookupEntry(mapId);
    if (!map || map->IsBattlegroundOrArena())
        return EXCLUDED_MAP;
    if (map->entrance_map >= 0 && data.continents.count(uint32(map->entrance_map)))
        return map->entrance_map;

    return EXCLUDED_MAP;
}

void KillCollectorMgr::LoadData()
{
    auto data = std::make_shared<Data>();

    if (QueryResult result = WorldDatabase.Query("SELECT map_id, continent_id FROM mod_kill_collector_continent_maps"))
    {
        do
        {
            Field* f = result->Fetch();
            data->continentByMap[f[0].Get<uint32>()] = f[1].Get<int32>();
        } while (result->NextRow());
    }

    if (QueryResult result = WorldDatabase.Query(
            "SELECT continent_id, creature_type, achievement_id FROM mod_kill_collector_achievements"))
    {
        do
        {
            Field* f = result->Fetch();
            uint32 const continent = f[0].Get<uint32>();
            uint32 const achievementId = f[2].Get<uint32>();
            data->achievementByBucket[BucketKey(continent, f[1].Get<uint8>())] = achievementId;
            data->bucketAchievements.insert(achievementId);
            data->continents.insert(continent);
        } while (result->NextRow());
    }

    FactionTemplateEntry const* teamFaction[TEAM_COUNT] =
    {
        sFactionTemplateStore.LookupEntry(ALLIANCE_PLAYER_FACTION_TEMPLATE),
        sFactionTemplateStore.LookupEntry(HORDE_PLAYER_FACTION_TEMPLATE)
    };

    // The expected set of a bucket: every creature entry spawned on the continent (its dungeons and raids
    // included) that a player of the team can attack. Spawns that only exist during a game event or outside
    // the normal phase, triggers, unattackable creatures and (by default) NPCs with a service flag are left
    // out: nobody could ever complete a bucket that holds them.
    std::unordered_map<uint64, std::unordered_set<uint32>> sets[TEAM_COUNT];
    if (teamFaction[0] && teamFaction[1])
    {
        if (QueryResult result = WorldDatabase.Query(
                "SELECT DISTINCT c.map, c.id, ct.type, ct.faction, ct.npcflag, ct.unit_flags, ct.flags_extra "
                "FROM creature c JOIN creature_template ct ON ct.entry = c.id "
                "WHERE (c.phaseMask & 1) <> 0 AND NOT EXISTS "
                "(SELECT 1 FROM game_event_creature gec WHERE gec.guid = c.guid AND gec.eventEntry > 0)"))
        {
            uint32 const unattackable = UNIT_FLAG_NON_ATTACKABLE | UNIT_FLAG_IMMUNE_TO_PC | UNIT_FLAG_NOT_SELECTABLE;
            do
            {
                Field* f = result->Fetch();
                uint32 const mapId = f[0].Get<uint16>();
                uint32 const entry = f[1].Get<uint32>();
                uint8 const type = f[2].Get<uint8>();
                uint32 const faction = f[3].Get<uint16>();
                uint32 const npcflag = f[4].Get<uint32>();
                uint32 const unitFlags = f[5].Get<uint32>();
                uint32 const flagsExtra = f[6].Get<uint32>();

                int32 const continent = ResolveContinent(*data, mapId);
                if (continent == EXCLUDED_MAP)
                    continue;

                uint64 const bucket = BucketKey(uint32(continent), type);
                if (!data->achievementByBucket.count(bucket))
                    continue;

                if ((unitFlags & unattackable) || (flagsExtra & CREATURE_FLAG_EXTRA_TRIGGER))
                    continue;
                if (_skipNpcFlagCreatures && npcflag)
                    continue;

                FactionTemplateEntry const* creatureFaction = sFactionTemplateStore.LookupEntry(faction);
                if (!creatureFaction)
                    continue;

                for (uint8 team = 0; team < TEAM_COUNT; ++team)
                    if (!creatureFaction->IsFriendlyTo(*teamFaction[team]))
                        sets[team][bucket].insert(entry);
            } while (result->NextRow());
        }
    }
    else
        LOG_ERROR("module", ">> KillCollector: FactionTemplate {} or {} is missing; no creature can count.",
                  ALLIANCE_PLAYER_FACTION_TEMPLATE, HORDE_PLAYER_FACTION_TEMPLATE);

    for (uint8 team = 0; team < TEAM_COUNT; ++team)
    {
        for (auto const& [bucket, entries] : sets[team])
        {
            data->expectedSize[team][bucket] = uint32(entries.size());
            for (uint32 entry : entries)
                data->bucketsByEntry[team][entry].push_back(bucket);
        }
    }

    // One line per continent: how many creatures each team can collect there.
    std::map<uint32, std::pair<uint32, uint32>> perContinent;
    for (uint32 continent : data->continents)
        perContinent[continent] = { 0, 0 };
    for (uint8 team = 0; team < TEAM_COUNT; ++team)
        for (auto const& [bucket, size] : data->expectedSize[team])
            (team ? perContinent[BucketContinent(bucket)].second : perContinent[BucketContinent(bucket)].first) += size;

    LOG_INFO("module", ">> KillCollector: {} continents, {} achievement buckets, {} map overrides.",
             data->continents.size(), data->achievementByBucket.size(), data->continentByMap.size());
    for (auto const& [continent, sizes] : perContinent)
        LOG_INFO("module", ">> KillCollector: continent {}: {} creatures for the Alliance, {} for the Horde.",
                 continent, sizes.first, sizes.second);
    LOG_INFO("module", ">> KillCollector: damage bonus {}% per earned achievement, meta achievement {}.",
             _damageBonusPct, _metaAchievementId);

    if (_tokenItemId && !sObjectMgr->GetItemTemplate(_tokenItemId))
        LOG_ERROR("module", ">> KillCollector: token item {} does not exist; first kills pay nothing.", _tokenItemId);
    if (_achievementsEnable && _metaAchievementId && !sAchievementStore.LookupEntry(_metaAchievementId))
        LOG_ERROR("module", ">> KillCollector: meta achievement {} is not in Achievement.dbc / achievement_dbc; it will not be granted.",
                  _metaAchievementId);

    std::lock_guard<std::mutex> guard(_lock);
    _data = data;
    for (auto& [guid, state] : _online)
        ComputeProgress(*data, state);
}

std::shared_ptr<KillCollectorMgr::Data const> KillCollectorMgr::GetData()
{
    std::lock_guard<std::mutex> guard(_lock);
    return _data;
}

void KillCollectorMgr::ComputeProgress(Data const& data, PlayerState& state)
{
    state.progress.clear();
    auto const& buckets = data.bucketsByEntry[state.team];
    for (uint32 entry : state.killed)
    {
        auto it = buckets.find(entry);
        if (it == buckets.end())
            continue;
        for (uint64 bucket : it->second)
            ++state.progress[bucket];
    }
}

std::vector<uint32> KillCollectorMgr::CompletedAchievements(Data const& data, PlayerState const& state)
{
    std::vector<uint32> done;
    for (auto const& [bucket, count] : state.progress)
    {
        auto size = data.expectedSize[state.team].find(bucket);
        if (size == data.expectedSize[state.team].end() || !size->second || count < size->second)
            continue;
        auto achievement = data.achievementByBucket.find(bucket);
        if (achievement != data.achievementByBucket.end())
            done.push_back(achievement->second);
    }
    return done;
}

void KillCollectorMgr::LoadState(Player* player)
{
    ObjectGuid::LowType const guid = player->GetGUID().GetCounter();

    PlayerState state;
    state.team = player->GetTeamId() == TEAM_HORDE ? 1 : 0;
    if (QueryResult result = CharacterDatabase.Query("SELECT entry FROM mod_kill_collector_kills WHERE guid = {}", guid))
    {
        do
        {
            state.killed.insert(result->Fetch()[0].Get<uint32>());
        } while (result->NextRow());
    }

    std::lock_guard<std::mutex> guard(_lock);
    if (_data)
        ComputeProgress(*_data, state);
    _online[guid] = std::move(state);
}

void KillCollectorMgr::OnLogin(Player* player)
{
    if (!_enabled || !player)
        return;

    LoadState(player);

    if (_achievementsEnable)
    {
        // A bucket can be complete at login: achievements were switched on later, or the bucket shrank.
        std::vector<uint32> done;
        {
            std::lock_guard<std::mutex> guard(_lock);
            auto it = _online.find(player->GetGUID().GetCounter());
            if (it != _online.end() && _data)
                done = CompletedAchievements(*_data, it->second);
        }
        GrantAchievements(player, done);

        // Also for a player that earned every bucket before the meta achievement existed.
        GrantMetaAchievement(player);
    }

    // The damage bonus needs only the earned achievements, so it works with AchievementsEnable off, too.
    RecomputeDamageBonus(player);
}

void KillCollectorMgr::OnLogout(Player* player)
{
    if (!player)
        return;
    std::lock_guard<std::mutex> guard(_lock);
    _online.erase(player->GetGUID().GetCounter());
}

void KillCollectorMgr::OnAchievementComplete(Player* player, uint32 achievementId)
{
    if (!_enabled || !player)
        return;

    std::shared_ptr<Data const> data = GetData();
    if (data && data->bucketAchievements.count(achievementId))
        RecomputeDamageBonus(player);
}

bool KillCollectorMgr::PassesKillFilters(Player* player, Creature* killed) const
{
    if (player->IsGameMaster())
        return false;
    if (killed->IsPet() || killed->IsTotem() || killed->IsCharmedOwnedByPlayerOrPlayer())
        return false;

    CreatureTemplate const* ct = killed->GetCreatureTemplate();
    if (!ct)
        return false;
    if (ct->type == CREATURE_TYPE_GAS_CLOUD)
        return false;
    if (ct->type == CREATURE_TYPE_CRITTER && !_includeCritters)
        return false;
    if (ct->type == CREATURE_TYPE_TOTEM && !_includeTotems)
        return false;
    if (ct->type == CREATURE_TYPE_NON_COMBAT_PET && !_includeNonCombatPets)
        return false;

    Map const* map = killed->GetMap();
    if (!map || map->IsBattlegroundOrArena())
        return false;
    if (map->Instanceable() ? !_includeInstances : !_includeOpenWorld)
        return false;

    if (_minLevelDelta > -100 && int32(killed->GetLevel()) - int32(player->GetLevel()) < _minLevelDelta)
        return false;

    return true;
}

void KillCollectorMgr::OnKillCredit(Player* player, Creature* killed)
{
    if (!_enabled || !player || !killed || !PassesKillFilters(player, killed))
        return;

    ObjectGuid::LowType const guid = player->GetGUID().GetCounter();
    uint32 const entry = killed->GetEntry();

    bool loaded;
    {
        std::lock_guard<std::mutex> guard(_lock);
        loaded = _online.count(guid) != 0;
    }
    if (!loaded)
    {
        LoadState(player); // the module was switched on after this player logged in
        RecomputeDamageBonus(player);
    }

    std::vector<uint32> earned;
    size_t uniqueKills = 0;
    {
        std::lock_guard<std::mutex> guard(_lock);
        auto it = _online.find(guid);
        if (it == _online.end())
            return;

        PlayerState& state = it->second;
        if (!state.killed.insert(entry).second)
            return; // collected before
        uniqueKills = state.killed.size();

        if (_data)
        {
            auto const& buckets = _data->bucketsByEntry[state.team];
            auto itBuckets = buckets.find(entry);
            if (itBuckets != buckets.end())
            {
                for (uint64 bucket : itBuckets->second)
                {
                    uint32 const count = ++state.progress[bucket];
                    auto size = _data->expectedSize[state.team].find(bucket);
                    if (_achievementsEnable && size != _data->expectedSize[state.team].end() && count == size->second)
                        earned.push_back(_data->achievementByBucket.at(bucket));
                }
            }
        }
    }

    CharacterDatabase.Execute(
        "INSERT IGNORE INTO mod_kill_collector_kills (guid, entry, map_id, creature_type, first_kill_time) "
        "VALUES ({}, {}, {}, {}, UNIX_TIMESTAMP())",
        guid, entry, killed->GetMapId(), uint32(killed->GetCreatureTemplate()->type));

    GiveTokens(player);

    if (_announceFirstKill)
        ChatHandler(player->GetSession()).PSendSysMessage(
            "|cff00ff00[Kill Collector]|r New creature collected: {} ({} in total).", killed->GetName(), uniqueKills);

    if (_logVerbose)
        LOG_INFO("module", "KillCollector: guid {} collected entry {} on map {} ({} in total).",
                 guid, entry, killed->GetMapId(), uniqueKills);

    if (GrantAchievements(player, earned))
    {
        RecomputeDamageBonus(player);
        GrantMetaAchievement(player);
    }
}

void KillCollectorMgr::Reset(Player* player)
{
    ObjectGuid::LowType const guid = player->GetGUID().GetCounter();
    CharacterDatabase.Execute("DELETE FROM mod_kill_collector_kills WHERE guid = {}", guid);

    std::lock_guard<std::mutex> guard(_lock);
    auto it = _online.find(guid);
    if (it != _online.end())
    {
        it->second.killed.clear();
        it->second.progress.clear();
    }
}

void KillCollectorMgr::GiveTokens(Player* player)
{
    if (!_tokenItemId || !_tokensPerKill || !sObjectMgr->GetItemTemplate(_tokenItemId))
        return;

    // What fits goes into the bags, the rest by mail, so a full bag never swallows a token.
    uint32 count = _tokensPerKill;
    uint32 noSpace = 0;
    ItemPosCountVec dest;
    if (player->CanStoreNewItem(NULL_BAG, NULL_SLOT, dest, _tokenItemId, count, &noSpace) != EQUIP_ERR_OK)
        count -= std::min(noSpace, count);

    uint32 toMail = _tokensPerKill;
    if (count && !dest.empty())
    {
        if (Item* item = player->StoreNewItem(dest, _tokenItemId, true))
        {
            player->SendNewItem(item, count, true, false);
            toMail -= count;
        }
    }

    if (!toMail)
        return;

    CharacterDatabaseTransaction trans = CharacterDatabase.BeginTransaction();
    MailDraft draft("Kill Collector", "Your bags were full when you collected a new creature, so your tokens come by mail.");
    if (Item* item = Item::CreateItem(_tokenItemId, toMail, player))
    {
        item->SaveToDB(trans);
        draft.AddItem(item);
    }
    draft.SendMailTo(trans, MailReceiver(player), MailSender(player, MAIL_STATIONERY_GM));
    CharacterDatabase.CommitTransaction(trans);
}

bool KillCollectorMgr::GrantAchievements(Player* player, std::vector<uint32> const& achievementIds)
{
    bool granted = false;
    for (uint32 id : achievementIds)
    {
        if (player->HasAchieved(id))
            continue;
        AchievementEntry const* achievement = sAchievementStore.LookupEntry(id);
        if (!achievement)
        {
            LOG_ERROR("module", "KillCollector: achievement {} is not in Achievement.dbc / achievement_dbc.", id);
            continue;
        }
        player->CompletedAchievement(achievement);
        // The core refuses for a game master in GM mode and for accounts that cannot earn achievements.
        granted = player->HasAchieved(id) || granted;
    }
    return granted;
}

bool KillCollectorMgr::GetMetaProgress(Player* player, uint32& done, uint32& total)
{
    done = 0;
    total = 0;
    if (!_metaAchievementId || !player)
        return false;

    std::shared_ptr<Data const> data = GetData();
    if (!data)
        return false;

    // A bucket nobody of the team can collect from (nothing of that type spawns there) is not asked for.
    uint8 const team = player->GetTeamId() == TEAM_HORDE ? 1 : 0;
    for (auto const& [bucket, achievementId] : data->achievementByBucket)
    {
        auto size = data->expectedSize[team].find(bucket);
        if (size == data->expectedSize[team].end() || !size->second)
            continue;
        ++total;
        if (player->HasAchieved(achievementId))
            ++done;
    }
    return total > 0;
}

bool KillCollectorMgr::HasMetaAchieved(Player* player) const
{
    return _metaAchievementId && player && player->HasAchieved(_metaAchievementId);
}

void KillCollectorMgr::GrantMetaAchievement(Player* player)
{
    if (!_achievementsEnable || !_metaAchievementId || player->IsGameMaster() || player->HasAchieved(_metaAchievementId))
        return;

    uint32 done = 0;
    uint32 total = 0;
    if (!GetMetaProgress(player, done, total) || done < total)
        return;

    AchievementEntry const* meta = sAchievementStore.LookupEntry(_metaAchievementId);
    if (!meta)
    {
        LOG_ERROR("module", "KillCollector: meta achievement {} is not in Achievement.dbc / achievement_dbc.", _metaAchievementId);
        return;
    }
    // The core's achievement reward (achievement_reward) gives the title.
    player->CompletedAchievement(meta);
}

void KillCollectorMgr::RecomputeDamageBonus(Player* player)
{
    if (!player)
        return;

    std::array<uint8, CREATURE_TYPE_SLOTS> earned{};
    if (std::shared_ptr<Data const> data = GetData())
    {
        for (auto const& [bucket, achievementId] : data->achievementByBucket)
        {
            uint8 const type = BucketType(bucket);
            if (type < earned.size() && earned[type] < 255 && player->HasAchieved(achievementId))
                ++earned[type];
        }
    }

    // One writer per player (its login, its kills, the commands run for it); the damage hooks only read.
    player->CustomData.GetDefault<KillCollectorBonus>(BONUS_DATA_KEY)->earned = earned;
}

std::string KillCollectorMgr::DescribeDamageBonus(Player* player) const
{
    std::string text;
    KillCollectorBonus const* bonus = player ? player->CustomData.Get<KillCollectorBonus>(BONUS_DATA_KEY) : nullptr;
    if (bonus && _damageBonusPct)
    {
        for (uint8 type = 0; type < CREATURE_TYPE_SLOTS; ++type)
        {
            if (!bonus->earned[type])
                continue;
            char const* plural = CreatureTypePlural(type);
            if (!text.empty())
                text += ", ";
            text += "+" + std::to_string(_damageBonusPct * bonus->earned[type]) + "% ";
            text += plural ? std::string(plural) : "type " + std::to_string(type);
        }
    }
    return text.empty() ? "none" : text;
}

bool KillCollectorMgr::GetProgress(Player* player, uint32& uniqueKills, std::vector<ContinentProgress>& out)
{
    std::lock_guard<std::mutex> guard(_lock);
    auto it = _online.find(player->GetGUID().GetCounter());
    if (it == _online.end() || !_data)
        return false;

    PlayerState const& state = it->second;
    uniqueKills = uint32(state.killed.size());

    std::map<uint32, ContinentProgress> byContinent;
    for (auto const& [bucket, achievementId] : _data->achievementByBucket)
    {
        auto size = _data->expectedSize[state.team].find(bucket);
        uint32 const expected = size == _data->expectedSize[state.team].end() ? 0 : size->second;
        if (!expected)
            continue; // nothing of that type to collect there

        auto progress = state.progress.find(bucket);
        uint32 const killed = progress == state.progress.end() ? 0 : progress->second;

        ContinentProgress& p = byContinent[BucketContinent(bucket)];
        p.continentId = BucketContinent(bucket);
        p.killed += std::min(killed, expected);
        p.expected += expected;
        ++p.achievementsTotal;
        if (killed >= expected)
            ++p.achievementsDone;
    }

    for (auto& [continent, p] : byContinent)
    {
        MapEntry const* map = sMapStore.LookupEntry(continent);
        char const* name = map ? map->name[sWorld->GetDefaultDbcLocale()] : nullptr;
        p.name = (name && *name) ? name : std::to_string(continent);
        out.push_back(p);
    }
    return true;
}
