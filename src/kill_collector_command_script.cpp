#include "Chat.h"
#include "Language.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "WorldSession.h"
#include "kill_collector_manager.h"

using namespace Acore::ChatCommands;

class KillCollectorCommandScript : public CommandScript
{
public:
    KillCollectorCommandScript() : CommandScript("KillCollectorCommandScript") { }

    ChatCommandTable GetCommands() const override
    {
        static ChatCommandTable killCollectorTable =
        {
            { "status", HandleStatus, SEC_PLAYER,        Console::No  },
            { "reload", HandleReload, SEC_ADMINISTRATOR, Console::Yes },
            { "reset",  HandleReset,  SEC_ADMINISTRATOR, Console::No  },
        };
        static ChatCommandTable commandTable =
        {
            { "killcollector", killCollectorTable },
        };
        return commandTable;
    }

    static bool HandleStatus(ChatHandler* handler)
    {
        Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
        if (!player)
            return false;

        if (!sKillCollectorMgr->IsEnabled())
        {
            handler->SendSysMessage("Kill Collector is switched off.");
            return true;
        }

        uint32 uniqueKills = 0;
        std::vector<KillCollectorMgr::ContinentProgress> continents;
        if (!sKillCollectorMgr->GetProgress(player, uniqueKills, continents))
        {
            handler->SendSysMessage("Kill Collector: no data yet.");
            return true;
        }

        handler->PSendSysMessage("Kill Collector: {} different creatures killed.", uniqueKills);
        for (KillCollectorMgr::ContinentProgress const& p : continents)
            handler->PSendSysMessage("  {}: {} of {} creatures, {} of {} achievements.",
                                     p.name, p.killed, p.expected, p.achievementsDone, p.achievementsTotal);
        return true;
    }

    // The named or selected player, else the invoker; only an online character.
    static bool HandleReset(ChatHandler* handler, Optional<PlayerIdentifier> player)
    {
        if (!player)
            player = PlayerIdentifier::FromTargetOrSelf(handler);
        Player* target = player ? player->GetConnectedPlayer() : nullptr;
        if (!target)
        {
            handler->SendErrorMessage(LANG_PLAYER_NOT_FOUND);
            return false;
        }

        sKillCollectorMgr->Reset(target);
        handler->PSendSysMessage("Kill Collector: {}'s collection reset.", target->GetName());
        return true;
    }

    static bool HandleReload(ChatHandler* handler)
    {
        if (!sKillCollectorMgr->IsEnabled())
        {
            handler->SendSysMessage("Kill Collector is switched off.");
            return true;
        }
        sKillCollectorMgr->LoadData();
        handler->SendSysMessage("Kill Collector: continents and creature lists rebuilt.");
        return true;
    }
};

void AddKillCollectorCommandScript()
{
    new KillCollectorCommandScript();
}
