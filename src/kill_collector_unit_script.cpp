#include "Creature.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "SpellAuraDefines.h"
#include "SpellInfo.h"
#include "Unit.h"
#include "kill_collector_manager.h"

#include <algorithm>
#include <limits>

// The damage bonus of the Kill Collector achievements: every earned bucket achievement pays
// KillCollector.DamageBonusPct percent damage against creatures of its creature type, wherever they are. The
// player's own damage counts and the damage of what it controls or owns (pets, guardians, totems).
//
// The hooks run for every blow in the world, so they stay cheap and take no lock: the per-type count of earned
// achievements lives on the Player (Object::CustomData, KillCollectorBonus), written by the manager at login and
// whenever a bucket achievement is completed, and only read here.
class KillCollectorUnitScript : public UnitScript
{
public:
    KillCollectorUnitScript() : UnitScript("KillCollectorUnitScript", true, {
        UNITHOOK_MODIFY_MELEE_DAMAGE,
        UNITHOOK_MODIFY_SPELL_DAMAGE_TAKEN,
        UNITHOOK_MODIFY_PERIODIC_DAMAGE_AURAS_TICK
    }) { }

    // Melee swings, before armor.
    void ModifyMeleeDamage(Unit* target, Unit* attacker, uint32& damage) override
    {
        Boost(target, attacker, damage);
    }

    // Direct spell damage, before armor, resistance and the critical strike.
    void ModifySpellDamageTaken(Unit* target, Unit* attacker, int32& damage, SpellInfo const* /*spellInfo*/) override
    {
        if (damage <= 0)
            return;

        uint32 boosted = uint32(damage);
        if (Boost(target, attacker, boosted))
            damage = int32(std::min<uint32>(boosted, uint32(std::numeric_limits<int32>::max())));
    }

    // Damage over time, before the tick's mitigation. The core calls this hook for healing ticks, too: only
    // the spells with a periodic damage aura count.
    void ModifyPeriodicDamageAurasTick(Unit* target, Unit* attacker, uint32& damage, SpellInfo const* spellInfo) override
    {
        if (!spellInfo ||
            (!spellInfo->HasAura(SPELL_AURA_PERIODIC_DAMAGE) && !spellInfo->HasAura(SPELL_AURA_PERIODIC_DAMAGE_PERCENT) &&
             !spellInfo->HasAura(SPELL_AURA_PERIODIC_LEECH)))
            return;

        Boost(target, attacker, damage);
    }

private:
    // true when the damage was raised. The target must be a creature that no player controls (no bonus against
    // players or their pets); the attacker is the player itself or what it controls or owns.
    static bool Boost(Unit* target, Unit* attacker, uint32& damage)
    {
        // The cheap tests first: most blows are creatures hitting players.
        if (!damage || !target || !attacker || !target->IsCreature() || target->IsControlledByPlayer())
            return false;

        uint32 const perAchievement = sKillCollectorMgr->DamageBonusPct();
        if (!perAchievement)
            return false;

        Player* player = attacker->GetCharmerOrOwnerPlayerOrPlayerItself();
        if (!player)
            return false;

        // Read only: the entry is created by the manager (login), never here.
        KillCollectorBonus const* bonus = player->CustomData.Get<KillCollectorBonus>(KillCollector::BONUS_DATA_KEY);
        if (!bonus)
            return false;

        uint32 const type = target->GetCreatureType();
        if (type >= bonus->earned.size() || !bonus->earned[type])
            return false;

        uint64 const percent = uint64(perAchievement) * bonus->earned[type];
        uint64 const boosted = uint64(damage) * (100 + percent) / 100;
        damage = uint32(std::min<uint64>(boosted, std::numeric_limits<uint32>::max()));
        return true;
    }
};

void AddKillCollectorUnitScript()
{
    new KillCollectorUnitScript();
}
