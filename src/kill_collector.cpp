#include "kill_collector_common.h"

void AddKillCollectorWorldScript();
void AddKillCollectorPlayerScript();

void AddKillCollectorScripts()
{
    // WorldScript first: it loads caches at OnAfterConfigLoad,
    // which the player hooks then read on the kill hot path.
    AddKillCollectorWorldScript();
    AddKillCollectorPlayerScript();
}
