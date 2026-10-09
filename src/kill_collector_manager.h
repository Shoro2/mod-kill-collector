#ifndef MOD_KILL_COLLECTOR_MANAGER_H
#define MOD_KILL_COLLECTOR_MANAGER_H

#include "kill_collector_common.h"
#include "ObjectGuid.h"

#include <memory>
#include <mutex>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

class Creature;
class Player;

class KillCollectorMgr
{
public:
    static KillCollectorMgr* instance();

    // Lifecycle
    void LoadConfig();
    // Continents, achievement buckets and the expected creature sets. Needs the DBC stores, so it runs at
    // startup (WorldScript::OnStartup) and on a config reload, never from the first config load.
    void LoadData();
    bool IsEnabled() const { return _enabled; }

    // Hooks
    void OnLogin(Player* player);
    void OnLogout(Player* player);
    void OnKillCredit(Player* player, Creature* killed);

    // .killcollector reset: forget everything the player has collected (achievements already earned stay).
    void Reset(Player* player);

    // .killcollector status: one line per continent.
    struct ContinentProgress
    {
        uint32 continentId = 0;
        std::string name;
        uint32 killed = 0;
        uint32 expected = 0;
        uint32 achievementsDone = 0;
        uint32 achievementsTotal = 0;
    };
    bool GetProgress(Player* player, uint32& uniqueKills, std::vector<ContinentProgress>& out);

private:
    KillCollectorMgr() = default;

    // Everything LoadData() builds; replaced as a whole on a reload, read through a shared_ptr copy.
    struct Data
    {
        std::unordered_map<uint32, int32> continentByMap;                  // overrides; EXCLUDED_MAP = never counts
        std::unordered_map<uint64, uint32> achievementByBucket;            // (continent, type) -> achievement id
        std::unordered_set<uint32> continents;                             // continents with at least one bucket
        std::unordered_map<uint64, uint32> expectedSize[KillCollector::TEAM_COUNT];
        std::unordered_map<uint32, std::vector<uint64>> bucketsByEntry[KillCollector::TEAM_COUNT];
    };

    struct PlayerState
    {
        uint8 team = 0;
        std::unordered_set<uint32> killed;                                 // every collected creature entry
        std::unordered_map<uint64, uint32> progress;                       // bucket -> collected entries in it
    };

    static int32 ResolveContinent(Data const& data, uint32 mapId);
    bool PassesKillFilters(Player* player, Creature* killed) const;
    static void ComputeProgress(Data const& data, PlayerState& state);
    static std::vector<uint32> CompletedAchievements(Data const& data, PlayerState const& state);
    void GiveTokens(Player* player);
    static void GrantAchievements(Player* player, std::vector<uint32> const& achievementIds);
    void LoadState(Player* player);

    // Config
    bool _enabled = false;
    uint32 _tokenItemId = KillCollector::DEFAULT_TOKEN_ITEM_ID;
    uint32 _tokensPerKill = 1;
    bool _announceFirstKill = true;
    bool _includeOpenWorld = true;
    bool _includeInstances = true;
    bool _includeCritters = false;
    bool _includeTotems = false;
    bool _includeNonCombatPets = false;
    int32 _minLevelDelta = -100;
    bool _skipNpcFlagCreatures = true;
    bool _achievementsEnable = false;
    bool _logVerbose = false;

    // _data and _online are shared between map threads and the world thread: every access holds _lock.
    std::mutex _lock;
    std::shared_ptr<Data const> _data;
    std::unordered_map<ObjectGuid::LowType, PlayerState> _online;
};

#define sKillCollectorMgr KillCollectorMgr::instance()

#endif // MOD_KILL_COLLECTOR_MANAGER_H
