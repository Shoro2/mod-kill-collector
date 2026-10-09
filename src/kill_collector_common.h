#ifndef MOD_KILL_COLLECTOR_COMMON_H
#define MOD_KILL_COLLECTOR_COMMON_H

#include "Define.h"

namespace KillCollector
{
    // Forgotten Land's custom item band (vault 06-custom-ids.md): 920200-920209 belong to this module.
    constexpr uint32 DEFAULT_TOKEN_ITEM_ID = 920200;

    // The two player teams (TeamId 0 = Alliance, 1 = Horde) each have their own expected sets:
    // a creature that is friendly to one team can only be collected by the other.
    constexpr uint8 TEAM_COUNT = 2;

    // Faction templates of a human (Alliance) and an orc (Horde) player: the reference for "can this team attack it".
    constexpr uint32 ALLIANCE_PLAYER_FACTION_TEMPLATE = 1;
    constexpr uint32 HORDE_PLAYER_FACTION_TEMPLATE = 2;

    // mod_kill_collector_continent_maps.continent_id of a map whose creatures never count.
    constexpr int32 EXCLUDED_MAP = -1;

    // An achievement bucket: one continent and one creature type.
    inline uint64 BucketKey(uint32 continentId, uint8 creatureType)
    {
        return (uint64(continentId) << 8) | creatureType;
    }

    inline uint32 BucketContinent(uint64 bucket)
    {
        return uint32(bucket >> 8);
    }
}

#endif // MOD_KILL_COLLECTOR_COMMON_H
