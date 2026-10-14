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
    // An achievement of the player is complete (also one a game master added): a bucket achievement changes the
    // damage bonus.
    void OnAchievementComplete(Player* player, uint32 achievementId);

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

    // The damage bonus: every earned bucket achievement pays _damageBonusPct percent against its creature type.
    // Percentage per achievement as configured (0 = off, also while the module is switched off); read on the hot
    // path of the damage hooks without a lock.
    uint32 DamageBonusPct() const { return _enabled ? _damageBonusPct : 0; }
    // Rebuilds the player's KillCollectorBonus (Object::CustomData) from the achievements it has earned.
    void RecomputeDamageBonus(Player* player);
    // "+10% beasts, +5% undead", or "none".
    std::string DescribeDamageBonus(Player* player) const;

    // The meta achievement: needs every bucket achievement whose bucket holds a creature the player's team can
    // attack. false when there is no meta achievement or no data; otherwise `done` of `total` are earned.
    bool GetMetaProgress(Player* player, uint32& done, uint32& total);
    bool HasMetaAchievement() const { return _metaAchievementId != 0; }
    bool HasMetaAchieved(Player* player) const;

private:
    KillCollectorMgr() = default;

    // Everything LoadData() builds; replaced as a whole on a reload, read through a shared_ptr copy.
    struct Data
    {
        std::unordered_map<uint32, int32> continentByMap;                  // overrides; EXCLUDED_MAP = never counts
        std::unordered_map<uint64, uint32> achievementByBucket;            // (continent, type) -> achievement id
        std::unordered_set<uint32> bucketAchievements;                     // the achievement ids of the buckets
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
    // true when at least one of the achievements was granted now.
    static bool GrantAchievements(Player* player, std::vector<uint32> const& achievementIds);
    // Grants the meta achievement when every bucket achievement of the player's team is earned.
    void GrantMetaAchievement(Player* player);
    std::shared_ptr<Data const> GetData();
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
    uint32 _damageBonusPct = KillCollector::DEFAULT_DAMAGE_BONUS_PCT;
    uint32 _metaAchievementId = KillCollector::META_ACHIEVEMENT_ID;
    bool _logVerbose = false;

    // _data and _online are shared between map threads and the world thread: every access holds _lock.
    std::mutex _lock;
    std::shared_ptr<Data const> _data;
    std::unordered_map<ObjectGuid::LowType, PlayerState> _online;
};

#define sKillCollectorMgr KillCollectorMgr::instance()

#endif // MOD_KILL_COLLECTOR_MANAGER_H
