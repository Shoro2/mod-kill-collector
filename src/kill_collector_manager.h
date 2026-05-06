#ifndef MOD_KILL_COLLECTOR_MANAGER_H
#define MOD_KILL_COLLECTOR_MANAGER_H

#include "kill_collector_common.h"

class KillCollectorMgr
{
public:
    static KillCollectorMgr* instance();

    // Lifecycle
    void LoadConfig();
    void LoadCachesFromWorldDB();
    void LoadPlayerStateOnLogin(Player* player);
    void FlushPlayerStateOnLogout(Player* player);

    // Hot path
    void HandleCreatureKill(Player* killer, Creature* killed);

    // Accessors
    bool IsEnabled() const { return _enabled; }

private:
    KillCollectorMgr() = default;

    struct PlayerKillSet
    {
        std::unordered_set<uint32> killedEntries;
        std::unordered_map<uint64, uint32> progressByBucket;
    };

    bool PassesFilters(Player* killer, Creature* killed) const;
    uint32 ResolveContinent(uint32 mapId) const;
    void AwardToken(Player* player);
    void TryCompleteAchievement(Player* player, uint32 continentId, uint8 creatureType);
    void PersistKill(ObjectGuid::LowType guid, uint32 entry, uint32 mapId, uint8 type);
    void PersistProgress(ObjectGuid::LowType guid, uint32 continentId, uint8 type, uint32 count, bool completed);

    // Config (populated from worldserver.conf via Config singleton)
    bool _enabled = false;
    uint32 _tokenItemId = KillCollector::DEFAULT_TOKEN_ITEM_ID;
    uint32 _tokensPerKill = 1;
    bool _announceFirstKill = true;
    bool _includeOpenWorld = true;
    bool _includeInstances = true;
    bool _includeCritters = false;
    bool _includeTotems = false;
    bool _includeNonCombatPets = false;
    bool _requireHostile = true;
    int32 _minLevelDelta = -10;
    bool _countPetKills = true;
    bool _achievementsEnable = true;
    uint32 _achievementIdBase = KillCollector::DEFAULT_ACHIEVEMENT_ID_BASE;
    bool _logVerbose = false;

    // Caches loaded once at OnAfterConfigLoad
    std::unordered_map<uint64, std::unordered_set<uint32>> _expectedMobs;
    std::unordered_map<uint64, uint32> _expectedTotals;
    std::unordered_map<uint64, uint32> _achievementByBucket;
    std::unordered_map<uint32, uint32> _mapToContinent;

    // Per-online-player cache (lazy-loaded on login, dropped on logout)
    std::unordered_map<ObjectGuid::LowType, PlayerKillSet> _online;
};

#define sKillCollectorMgr KillCollectorMgr::instance()

#endif // MOD_KILL_COLLECTOR_MANAGER_H
