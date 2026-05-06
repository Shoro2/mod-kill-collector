#include "kill_collector_common.h"
#include "kill_collector_manager.h"

class KillCollectorWorldScript : public WorldScript
{
public:
    KillCollectorWorldScript() : WorldScript("KillCollectorWorldScript") { }

    void OnAfterConfigLoad(bool /*reload*/) override
    {
        sKillCollectorMgr->LoadConfig();
        if (sKillCollectorMgr->IsEnabled())
            sKillCollectorMgr->LoadCachesFromWorldDB();
    }
};

void AddKillCollectorWorldScript()
{
    new KillCollectorWorldScript();
}
