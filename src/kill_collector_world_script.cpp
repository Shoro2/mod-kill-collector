#include "ScriptMgr.h"
#include "kill_collector_manager.h"

class KillCollectorWorldScript : public WorldScript
{
public:
    KillCollectorWorldScript() : WorldScript("KillCollectorWorldScript", {
        WORLDHOOK_ON_AFTER_CONFIG_LOAD,
        WORLDHOOK_ON_STARTUP
    }) { }

    // The first config load runs before the DBC stores exist, so the data loads at startup;
    // a later `.reload config` rebuilds it right away.
    void OnAfterConfigLoad(bool reload) override
    {
        sKillCollectorMgr->LoadConfig();
        if (reload && sKillCollectorMgr->IsEnabled())
            sKillCollectorMgr->LoadData();
    }

    void OnStartup() override
    {
        if (sKillCollectorMgr->IsEnabled())
            sKillCollectorMgr->LoadData();
    }
};

void AddKillCollectorWorldScript()
{
    new KillCollectorWorldScript();
}
