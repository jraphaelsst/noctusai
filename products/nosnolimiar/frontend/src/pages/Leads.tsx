/**
 * `/leads` (Funil, the default) and `/leads/lista` (Lista) -- the seed leads organ.
 *
 * One page component holds the filters, so Funil and Lista SHARE them (search, origin, first-contact range): switch
 * view and the same filter is still on. Create / edit / delete are the organ's own (full CRUD). "Abrir conversa"
 * on a lead opens the inbox on that chat (`/conversas?chat=`). A closed lead (stage `fechado`) is a patient: "Ver
 * paciente" opens it (`/pacientes?lead=` resolves the conversion).
 */
import * as React from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { LeadsBoard, LeadsList, type Lead, type LeadFiltersState } from "@noctusai/lib";
import type { DetailAction } from "@noctusai/lib/components";
import { HeartHandshake } from "lucide-react";
import { Tabs, TabsList, TabsTrigger } from "@noctusai/lib/design-system";

import { conversationPath, leadsHooks, patientOfLeadPath } from "@/lib/crm";

const LISTA_PATH = "/leads/lista";
const FUNIL_PATH = "/leads";
/** The stage whose leads are patients (the backend converts on entering it). */
const STAGE_PACIENTE = "fechado";

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

  const extraActions = React.useCallback(
    (lead: Lead): DetailAction[] =>
      lead.stage === STAGE_PACIENTE
        ? [
            {
              label: "Ver paciente",
              variant: "outline",
              icon: <HeartHandshake className="mr-1 h-4 w-4" />,
              onClick: () => navigate(patientOfLeadPath(lead.id)),
              testId: "lead-detail-ver-paciente",
            },
          ]
        : [],
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
        <LeadsBoard hooks={leadsHooks} filters={filters} onFiltersChange={setFilters} onOpenConversation={openConversation} extraActions={extraActions} />
      ) : (
        <LeadsList hooks={leadsHooks} filters={filters} onFiltersChange={setFilters} onOpenConversation={openConversation} extraActions={extraActions} />
      )}
    </div>
  );
}
