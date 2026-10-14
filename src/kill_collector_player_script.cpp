#include "DatabaseEnv.h"
#include "KillRewarder.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "Unit.h"
#include "kill_collector_manager.h"

class KillCollectorPlayerScript : public PlayerScript
{
public:
    KillCollectorPlayerScript() : PlayerScript("KillCollectorPlayerScript", {
        PLAYERHOOK_ON_LOGIN,
        PLAYERHOOK_ON_LOGOUT,
        PLAYERHOOK_ON_REWARD_KILL_REWARDER,
        PLAYERHOOK_ON_ACHI_COMPLETE,
        PLAYERHOOK_ON_DELETE_FROM_DB
    }) { }

    void OnPlayerLogin(Player* player) override
    {
        sKillCollectorMgr->OnLogin(player);
    }

    void OnPlayerLogout(Player* player) override
    {
        sKillCollectorMgr->OnLogout(player);
    }

    // Fires for every player the kill rewards: the killer, the tapping group's members in range, and the owner
    // of a pet or totem that landed the blow - so a healer in the group collects the creature too.
    void OnPlayerRewardKillRewarder(Player* player, KillRewarder* rewarder, bool /*isDungeon*/, float& /*rate*/) override
    {
        if (Unit* victim = rewarder ? rewarder->GetVictim() : nullptr)
            if (Creature* creature = victim->ToCreature())
                sKillCollectorMgr->OnKillCredit(player, creature);
    }

    // Any completed achievement, also one a game master added: a bucket achievement raises the damage bonus.
    void OnPlayerAchievementComplete(Player* player, AchievementEntry const* achievement) override
    {
        if (achievement)
            sKillCollectorMgr->OnAchievementComplete(player, achievement->ID);
    }

    void OnPlayerDeleteFromDB(CharacterDatabaseTransaction trans, uint32 guid) override
    {
        trans->Append("DELETE FROM mod_kill_collector_kills WHERE guid = {}", guid);
    }
};

void AddKillCollectorPlayerScript()
{
    new KillCollectorPlayerScript();
}
