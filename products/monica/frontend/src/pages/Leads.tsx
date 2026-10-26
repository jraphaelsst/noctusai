/**
 * `/leads` (Funil, the default) and `/leads/lista` (Lista) -- the seed leads organ.
 *
 * One page component holds the filters, so Funil and Lista SHARE them (search, origin, first-contact range): switch
 * view and the same filter is still on. Create / edit / delete are the organ's own (full CRUD). "Abrir conversa"
 * on a lead opens the inbox on that chat (`/conversas?chat=`).
 */
import * as React from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { LeadsBoard, LeadsList, type Lead, type LeadFiltersState } from "@noctusai/lib";
import { Tabs, TabsList, TabsTrigger } from "@noctusai/lib/design-system";

import { conversationPath, leadsHooks } from "@/lib/crm";

const LISTA_PATH = "/leads/lista";
const FUNIL_PATH = "/leads";

export default function Leads() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [filters, setFilters] = React.useState<LeadFiltersState>({});
  const view = pathname.replace(/\/+$/, "") === LISTA_PATH ? "lista" : "funil";

  const openConversation = React.useCallback(
    (lead: Lead) => {
      if (lead.whatsapp_chat_id) navigate(conversationPath(lead.whatsapp_chat_id));
    },
    [navigate],
  );

  return (
    <div className="space-y-4" data-testid="leads-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Leads</h1>
          <p className="text-sm text-muted-foreground">Quem chegou até você e em que ponto da conversa está.</p>
        </div>
        <Tabs value={view} onValueChange={(v) => navigate(v === "lista" ? LISTA_PATH : FUNIL_PATH)}>
          <TabsList aria-label="Visualização dos leads">
            <TabsTrigger value="funil" data-testid="leads-view-funil">Funil</TabsTrigger>
            <TabsTrigger value="lista" data-testid="leads-view-lista">Lista</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>
      {view === "funil" ? (
        <LeadsBoard hooks={leadsHooks} filters={filters} onFiltersChange={setFilters} onOpenConversation={openConversation} />
      ) : (
        <LeadsList hooks={leadsHooks} filters={filters} onFiltersChange={setFilters} onOpenConversation={openConversation} />
      )}
    </div>
  );
}
