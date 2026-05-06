#include "kill_collector_manager.h"

KillCollectorMgr* KillCollectorMgr::instance()
{
    static KillCollectorMgr inst;
    return &inst;
}

void KillCollectorMgr::LoadConfig()
{
    _enabled            = sConfigMgr->GetOption<bool>("KillCollector.Enable", false);
    _tokenItemId        = sConfigMgr->GetOption<uint32>("KillCollector.TokenItemId", KillCollector::DEFAULT_TOKEN_ITEM_ID);
    _tokensPerKill      = sConfigMgr->GetOption<uint32>("KillCollector.TokensPerFirstKill", 1);
    _announceFirstKill  = sConfigMgr->GetOption<bool>("KillCollector.AnnounceFirstKill", true);

    _includeOpenWorld    = sConfigMgr->GetOption<bool>("KillCollector.IncludeOpenWorld", true);
    _includeInstances    = sConfigMgr->GetOption<bool>("KillCollector.IncludeInstances", true);
    _includeCritters     = sConfigMgr->GetOption<bool>("KillCollector.IncludeCritters", false);
    _includeTotems       = sConfigMgr->GetOption<bool>("KillCollector.IncludeTotems", false);
    _includeNonCombatPets= sConfigMgr->GetOption<bool>("KillCollector.IncludeNonCombatPets", false);
    _requireHostile      = sConfigMgr->GetOption<bool>("KillCollector.RequireHostile", true);
    _minLevelDelta       = sConfigMgr->GetOption<int32>("KillCollector.MinLevelDelta", -10);
    _countPetKills       = sConfigMgr->GetOption<bool>("KillCollector.CountPetKills", true);

    _achievementsEnable  = sConfigMgr->GetOption<bool>("KillCollector.AchievementsEnable", true);
    _achievementIdBase   = sConfigMgr->GetOption<uint32>("KillCollector.AchievementIdBase", KillCollector::DEFAULT_ACHIEVEMENT_ID_BASE);
    _logVerbose          = sConfigMgr->GetOption<bool>("KillCollector.LogVerbose", false);
}

void KillCollectorMgr::LoadCachesFromWorldDB()
{
    _expectedMobs.clear();
    _expectedTotals.clear();
    _achievementByBucket.clear();
    _mapToContinent.clear();

    if (QueryResult result = WorldDatabase.Query("SELECT continent_id, map_id FROM mod_kill_collector_continent_maps"))
    {
        do
        {
            Field* f = result->Fetch();
            _mapToContinent[f[1].Get<uint32>()] = f[0].Get<uint32>();
        } while (result->NextRow());
    }

    if (QueryResult result = WorldDatabase.Query("SELECT continent_id, creature_type, expected_total, achievement_id FROM mod_kill_collector_totals"))
    {
        do
        {
            Field* f = result->Fetch();
            uint32 continent = f[0].Get<uint32>();
            uint8 type = f[1].Get<uint8>();
            uint64 bucket = KillCollector::BucketKey(continent, type);
            _expectedTotals[bucket] = f[2].Get<uint32>();
            _achievementByBucket[bucket] = f[3].Get<uint32>();
        } while (result->NextRow());
    }

    // Build expected-mob set: distinct creature_template.entry per (continent, type),
    // restricted to entries that are actually spawned on tracked maps.
    if (QueryResult result = WorldDatabase.Query(
        "SELECT DISTINCT ct.entry, ct.type, mkc.continent_id "
        "FROM creature_template ct "
        "JOIN creature c ON c.id1 = ct.entry "
        "JOIN mod_kill_collector_continent_maps mkc ON mkc.map_id = c.map "
        "WHERE ct.type IN (1,2,3,4,5,6,7,9,10)"))
    {
        do
        {
            Field* f = result->Fetch();
            uint32 entry = f[0].Get<uint32>();
            uint8 type = f[1].Get<uint8>();
            uint32 continent = f[2].Get<uint32>();
            _expectedMobs[KillCollector::BucketKey(continent, type)].insert(entry);
        } while (result->NextRow());
    }

    size_t totalEntries = 0;
    for (auto const& kv : _expectedMobs)
        totalEntries += kv.second.size();

    LOG_INFO("module",
             ">> KillCollector: loaded {} continent-map mappings, {} buckets, {} expected mob entries.",
             _mapToContinent.size(), _expectedTotals.size(), totalEntries);
}

uint32 KillCollectorMgr::ResolveContinent(uint32 mapId) const
{
    auto it = _mapToContinent.find(mapId);
    return (it != _mapToContinent.end()) ? it->second : 0xFFFFFFFFu;
}

void KillCollectorMgr::LoadPlayerStateOnLogin(Player* player)
{
    if (!player)
        return;

    ObjectGuid::LowType guid = player->GetGUID().GetCounter();
    PlayerKillSet& s = _online[guid];
    s.killedEntries.clear();
    s.progressByBucket.clear();

    if (QueryResult result = CharacterDatabase.Query("SELECT entry FROM mod_kill_collector_kills WHERE guid = {}", guid))
    {
        do
        {
            s.killedEntries.insert(result->Fetch()[0].Get<uint32>());
        } while (result->NextRow());
    }

    if (QueryResult result = CharacterDatabase.Query(
            "SELECT continent_id, creature_type, kill_count FROM mod_kill_collector_progress WHERE guid = {}", guid))
    {
        do
        {
            Field* f = result->Fetch();
            s.progressByBucket[KillCollector::BucketKey(f[0].Get<uint32>(), f[1].Get<uint8>())] = f[2].Get<uint32>();
        } while (result->NextRow());
    }
}

void KillCollectorMgr::FlushPlayerStateOnLogout(Player* player)
{
    if (!player)
        return;
    _online.erase(player->GetGUID().GetCounter());
}

bool KillCollectorMgr::PassesFilters(Player* killer, Creature* killed) const
{
    if (!killer || !killed)
        return false;
    if (killed->IsPet() || killed->IsTotem())
        return false;

    CreatureTemplate const* ct = killed->GetCreatureTemplate();
    if (!ct)
        return false;

    if (!_includeCritters && ct->type == CREATURE_TYPE_CRITTER)
        return false;
    if (!_includeTotems && ct->type == CREATURE_TYPE_TOTEM)
        return false;
    if (!_includeNonCombatPets && ct->type == CREATURE_TYPE_NON_COMBAT_PET)
        return false;

    bool const inInstance = killed->GetMap() && killed->GetMap()->Instanceable();
    if (inInstance && !_includeInstances)
        return false;
    if (!inInstance && !_includeOpenWorld)
        return false;

    if (_requireHostile && !killed->IsHostileTo(killer))
        return false;

    if (_minLevelDelta > -100)
    {
        int32 delta = static_cast<int32>(killed->GetLevel()) - static_cast<int32>(killer->GetLevel());
        if (delta < _minLevelDelta)
            return false;
    }

    return true;
}

void KillCollectorMgr::HandleCreatureKill(Player* killer, Creature* killed)
{
    if (!_enabled || !PassesFilters(killer, killed))
        return;

    uint32 entry = killed->GetEntry();
    uint8 type = killed->GetCreatureTemplate()->type;
    uint32 mapId = killer->GetMapId();
    uint32 continent = ResolveContinent(mapId);

    ObjectGuid::LowType guid = killer->GetGUID().GetCounter();
    PlayerKillSet& s = _online[guid];

    if (!s.killedEntries.insert(entry).second)
        return; // already collected

    PersistKill(guid, entry, mapId, type);
    AwardToken(killer);

    if (_announceFirstKill && killer->GetSession())
        ChatHandler(killer->GetSession()).PSendSysMessage(
            "|cff00ff00[Kill Collector]|r New unique kill! +{} token.", _tokensPerKill);

    if (_logVerbose)
        LOG_INFO("module", "KillCollector: guid={} entry={} type={} map={} continent={}",
                 guid, entry, uint32(type), mapId, continent);

    if (continent == 0xFFFFFFFFu || !_achievementsEnable)
        return;

    uint64 bucket = KillCollector::BucketKey(continent, type);
    auto itExpected = _expectedMobs.find(bucket);
    if (itExpected == _expectedMobs.end() || !itExpected->second.count(entry))
        return; // entry not part of any tracked achievement bucket

    uint32 newCount = ++s.progressByBucket[bucket];
    auto itTotal = _expectedTotals.find(bucket);
    bool const completed = (itTotal != _expectedTotals.end() && newCount >= itTotal->second);
    PersistProgress(guid, continent, type, newCount, completed);

    if (completed)
        TryCompleteAchievement(killer, continent, type);
}

void KillCollectorMgr::AwardToken(Player* player)
{
    if (_tokensPerKill > 0 && _tokenItemId > 0)
        player->AddItem(_tokenItemId, _tokensPerKill);
}

void KillCollectorMgr::TryCompleteAchievement(Player* player, uint32 continentId, uint8 creatureType)
{
    auto it = _achievementByBucket.find(KillCollector::BucketKey(continentId, creatureType));
    if (it == _achievementByBucket.end())
        return;

    AchievementEntry const* ach = sAchievementStore.LookupEntry(it->second);
    if (!ach)
    {
        LOG_WARN("module",
                 "KillCollector: configured achievement_id {} not found in DBC (continent={}, type={}).",
                 it->second, continentId, uint32(creatureType));
        return;
    }

    player->GetAchievementMgr()->CompletedAchievement(ach);
}

void KillCollectorMgr::PersistKill(ObjectGuid::LowType guid, uint32 entry, uint32 mapId, uint8 type)
{
    CharacterDatabase.Execute(
        "INSERT IGNORE INTO mod_kill_collector_kills (guid, entry, map_id, creature_type, first_kill_time) "
        "VALUES ({}, {}, {}, {}, UNIX_TIMESTAMP())",
        guid, entry, mapId, uint32(type));
}

void KillCollectorMgr::PersistProgress(ObjectGuid::LowType guid, uint32 continentId, uint8 type, uint32 count, bool completed)
{
    if (completed)
    {
        CharacterDatabase.Execute(
            "INSERT INTO mod_kill_collector_progress (guid, continent_id, creature_type, kill_count, completed_at) "
            "VALUES ({}, {}, {}, {}, UNIX_TIMESTAMP()) "
            "ON DUPLICATE KEY UPDATE kill_count = VALUES(kill_count), completed_at = VALUES(completed_at)",
            guid, continentId, uint32(type), count);
    }
    else
    {
        CharacterDatabase.Execute(
            "INSERT INTO mod_kill_collector_progress (guid, continent_id, creature_type, kill_count) "
            "VALUES ({}, {}, {}, {}) "
            "ON DUPLICATE KEY UPDATE kill_count = VALUES(kill_count)",
            guid, continentId, uint32(type), count);
    }
}
