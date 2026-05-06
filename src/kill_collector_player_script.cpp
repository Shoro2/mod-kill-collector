#include "kill_collector_common.h"
#include "kill_collector_manager.h"

class KillCollectorPlayerScript : public PlayerScript
{
public:
    KillCollectorPlayerScript() : PlayerScript("KillCollectorPlayerScript") { }

    void OnPlayerLogin(Player* player) override
    {
        if (sKillCollectorMgr->IsEnabled())
            sKillCollectorMgr->LoadPlayerStateOnLogin(player);
    }

    void OnPlayerLogout(Player* player) override
    {
        sKillCollectorMgr->FlushPlayerStateOnLogout(player);
    }

    // Hook fired when a Player lands the killing blow on a Creature.
    void OnPlayerCreatureKill(Player* killer, Creature* killed) override
    {
        sKillCollectorMgr->HandleCreatureKill(killer, killed);
    }
};

void AddKillCollectorPlayerScript()
{
    new KillCollectorPlayerScript();
}
