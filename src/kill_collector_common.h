#ifndef MOD_KILL_COLLECTOR_COMMON_H
#define MOD_KILL_COLLECTOR_COMMON_H

#include "DataMap.h"
#include "Define.h"

#include <array>
#include <string>

namespace KillCollector
{
    // Forgotten Land's custom item band (vault 06-custom-ids.md): 920200-920209 belong to this module.
    constexpr uint32 DEFAULT_TOKEN_ITEM_ID = 920200;

    // The meta achievement "N3rd": earned once every bucket achievement the player's team can earn is
    // (KillCollector.MetaAchievementId, 0 = none). Its reward is the title "N3rd %s" (CharTitles 178, bit 143).
    constexpr uint32 META_ACHIEVEMENT_ID = 30051;

    // Every earned bucket achievement pays this many percent damage against its creature type
    // (KillCollector.DamageBonusPct, 0 = no bonus).
    constexpr uint32 DEFAULT_DAMAGE_BONUS_PCT = 5;

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

    inline uint8 BucketType(uint64 bucket)
    {
        return uint8(bucket & 0xFF);
    }

    // The damage bonus of one player, kept on the Player itself (Object::CustomData) so the damage hooks need no
    // lock: for each creature type (CreatureType, 0-15) the number of earned bucket achievements of that type.
    // The percentage is that number times KillCollector.DamageBonusPct, read when the damage is dealt.
    constexpr uint8 CREATURE_TYPE_SLOTS = 16;

    // Key of the bonus in Object::CustomData (at most 15 characters: no heap allocation, however it is passed).
    inline std::string const BONUS_DATA_KEY = "kill-collector";

    inline char const* CreatureTypePlural(uint8 creatureType)
    {
        switch (creatureType)
        {
            case 1:  return "beasts";
            case 2:  return "dragonkin";
            case 3:  return "demons";
            case 4:  return "elementals";
            case 5:  return "giants";
            case 6:  return "undead";
            case 7:  return "humanoids";
            case 9:  return "mechanicals";
            case 10: return "oddities";
            default: return nullptr;
        }
    }
}

struct KillCollectorBonus : public DataMap::Base
{
    std::array<uint8, KillCollector::CREATURE_TYPE_SLOTS> earned{};
};

#endif // MOD_KILL_COLLECTOR_COMMON_H
