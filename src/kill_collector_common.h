#ifndef MOD_KILL_COLLECTOR_COMMON_H
#define MOD_KILL_COLLECTOR_COMMON_H

#include "ScriptMgr.h"
#include "Player.h"
#include "Creature.h"
#include "CreatureData.h"
#include "ObjectGuid.h"
#include "Config.h"
#include "Log.h"
#include "DatabaseEnv.h"
#include "Chat.h"
#include "AchievementMgr.h"
#include "DBCStores.h"
#include "SharedDefines.h"

#include <unordered_map>
#include <unordered_set>

namespace KillCollector
{
    constexpr uint32 DEFAULT_TOKEN_ITEM_ID = 80001;
    constexpr uint32 DEFAULT_ACHIEVEMENT_ID_BASE = 30000;

    inline uint64 BucketKey(uint32 continentId, uint8 creatureType)
    {
        return (static_cast<uint64>(continentId) << 8) | static_cast<uint64>(creatureType);
    }
}

#endif // MOD_KILL_COLLECTOR_COMMON_H
