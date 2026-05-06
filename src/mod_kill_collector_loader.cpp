#include "kill_collector_common.h"

void AddKillCollectorScripts();

// Entry point invoked by the module loader. The function name is
// the folder name with `-` replaced by `_`.
void Addmod_kill_collectorScripts()
{
    AddKillCollectorScripts();
}
