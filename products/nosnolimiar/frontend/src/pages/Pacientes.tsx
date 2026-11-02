/**
 * `/pacientes/*` -- the seed clients organ (noun "Paciente" comes from the backend's `ClientsConfig`):
 *   - `/pacientes`          the list (search, situação, etiquetas); `?lead=<id>` resolves the patient converted from
 *                           that lead (`GET /api/clients?lead_id=`) and redirects to it;
 *   - `/pacientes/agenda`   the week agenda across every patient;
 *   - `/pacientes/:id`      one patient: Sessões · Agenda fixa · Financeiro · Dados (`?aba=` keeps the tab in the URL).
 * `isAdmin` is the UX gate only -- the server enforces admin on deletes and payments.
 */
import * as React from "react";
import { Navigate, Route, Routes, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ClientDetailPage, ClientsAgenda, ClientsList, type ClientDetailTab } from "@noctusai/lib";
import { Tabs, TabsList, TabsTrigger, useIsOrgAdmin } from "@noctusai/lib/design-system";

import { clientsHooks, PACIENTES_PATH, patientPath } from "@/lib/crm";

const AGENDA_PATH = `${PACIENTES_PATH}/agenda`;
const TABS: ClientDetailTab[] = ["sessoes", "agenda", "financeiro", "dados"];

function PacientesHeader({ view }: { view: "lista" | "agenda" }) {
  const navigate = useNavigate();
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Pacientes</h1>
        <p className="text-sm text-muted-foreground">Quem você atende: sessões, agenda fixa e financeiro.</p>
      </div>
      <Tabs value={view} onValueChange={(v) => navigate(v === "agenda" ? AGENDA_PATH : PACIENTES_PATH)}>
        <TabsList aria-label="Visualização dos pacientes">
          <TabsTrigger value="lista" data-testid="pacientes-view-lista">Lista</TabsTrigger>
          <TabsTrigger value="agenda" data-testid="pacientes-view-agenda">Agenda</TabsTrigger>
        </TabsList>
      </Tabs>
    </div>
  );
}

/** `?lead=<id>`: the patient converted from that lead, or an honest "not yet" (never a silent empty list). */
function LeadRedirect({ leadId }: { leadId: string }) {
  const found = clientsHooks.useClientByLead(leadId);
  if (found.data) return <Navigate to={patientPath(found.data.id)} replace />;
  if (found.isError) {
    return (
      <p className="text-sm text-destructive" data-testid="pacientes-lead-erro">
        Não foi possível localizar o paciente deste lead.
      </p>
    );
  }
  if (found.data === null) {
    return (
      <p className="rounded-md border p-3 text-sm text-muted-foreground" data-testid="pacientes-lead-sem-paciente">
        Este lead ainda não virou paciente. Ele vira paciente automaticamente ao entrar na etapa Fechado.
      </p>
    );
  }
  return (
    <p className="text-sm text-muted-foreground" role="status" data-testid="pacientes-lead-carregando">
      Abrindo o paciente…
    </p>
  );
}

function Lista() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const leadId = params.get("lead");
  return (
    <div className="space-y-4" data-testid="pacientes-page">
      <PacientesHeader view="lista" />
      {leadId && <LeadRedirect leadId={leadId} />}
      <ClientsList hooks={clientsHooks} onOpenClient={(c) => navigate(patientPath(c.id))} />
    </div>
  );
}

function Agenda() {
  const navigate = useNavigate();
  return (
    <div className="space-y-4" data-testid="pacientes-agenda-page">
      <PacientesHeader view="agenda" />
      <ClientsAgenda hooks={clientsHooks} onOpenClient={(id) => navigate(patientPath(id))} />
    </div>
  );
}

function Detalhe() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const aba = params.get("aba");
  const tab = TABS.includes(aba as ClientDetailTab) ? (aba as ClientDetailTab) : "sessoes";
  return (
    <ClientDetailPage
      hooks={clientsHooks}
      clientId={id}
      isAdmin={useIsOrgAdmin()}
      tab={tab}
      onTabChange={(next) => setParams(next === "sessoes" ? {} : { aba: next }, { replace: true })}
      onBack={() => navigate(PACIENTES_PATH)}
      onDeleted={() => navigate(PACIENTES_PATH, { replace: true })}
    />
  );
}

export default function Pacientes() {
  return (
    <Routes>
      <Route index element={<Lista />} />
      <Route path="agenda" element={<Agenda />} />
      <Route path=":id" element={<Detalhe />} />
    </Routes>
  );
}
