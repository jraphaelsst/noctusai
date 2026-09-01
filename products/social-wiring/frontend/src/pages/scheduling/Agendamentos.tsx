/**
 * Agendamentos — the UI for the `scheduling` module (`/api/scheduling/*`).
 *
 * The module shipped 15 endpoints and no frontend at all; this page is that
 * frontend. Four tabs, covering every route:
 *
 *   Agenda        · GET /appointments (+ status filter) · GET /appointment-requests
 *   Propor        · POST /propose
 *   Cadastros     · GET|POST|PATCH /condominiums · /properties · /services · /users
 *   Identidades   · GET /pending-chat-identities · PATCH /pending-chat-identities/{id}
 *
 * The four Cadastros surfaces are driven by the canonical `<ResourceManager/>`
 * organ (`@noctusai/lib/components`) rather than hand-rolled CRUD — the
 * page-scoped-CRUD rule. The module exposes no DELETE, so every one sets
 * `canDelete={false}`; deactivating is the `active` flag on the edit form.
 *
 * Route: /agendamentos (App.tsx lazy routes + a `agendamentos` status_pagina
 * row from migration 084).
 */
import { useMemo, useState } from "react";
import { toast } from "sonner";
import {
  AlertCircle,
  CalendarClock,
  CheckCircle2,
  Inbox,
  Sparkles,
  UserCheck,
  XCircle,
} from "lucide-react";

import { ResourceManager } from "@noctusai/lib/components";
import { api } from "@/lib/api";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import {
  useAppointmentRequests,
  useAppointments,
  usePendingChatIdentities,
  useProposeSlots,
  useResolvePendingChatIdentity,
  useSchedulingCondominiums,
  useSchedulingProperties,
  useSchedulingUsers,
  type Appointment,
  type AppointmentStatus,
  type Condominium,
  type PendingChatIdentity,
  type ProposedSlot,
  type SchedulingProperty,
  type SchedulingService,
  type SchedulingUser,
} from "@/hooks/useScheduling";

// ─── Formatting ──────────────────────────────────────────────────────────────

function fmtDateTime(value: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString("pt-BR");
}

function fmtDate(value: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString("pt-BR");
}

const APPOINTMENT_STATUS_LABEL: Record<AppointmentStatus, string> = {
  scheduled: "Agendado",
  completed: "Concluído",
  cancelled: "Cancelado",
  no_show: "Não compareceu",
  rescheduled: "Remarcado",
};

const REQUEST_STATUS_LABEL: Record<string, string> = {
  collecting_details: "Coletando dados",
  pending_confirmation: "Aguardando confirmação",
  confirmed: "Confirmado",
  cancelled: "Cancelado",
  expired: "Expirado",
};

const ROLE_LABEL: Record<string, string> = {
  real_estate_agent: "Corretor",
  media_crew: "Equipe de mídia",
  admin: "Administrador",
};

// ─── Shared state blocks ─────────────────────────────────────────────────────

function ListSkeleton({ testId }: { testId: string }) {
  return (
    <div className="space-y-2" data-testid={testId}>
      {[1, 2, 3, 4].map((i) => (
        <Skeleton key={i} className="h-14 w-full" />
      ))}
    </div>
  );
}

function ErrorBlock({ testId, message }: { testId: string; message: string }) {
  return (
    <Card className="border-destructive" data-testid={testId}>
      <CardContent className="flex items-center gap-3 pt-6">
        <AlertCircle className="h-5 w-5 text-destructive" />
        <p className="text-sm text-destructive">{message}</p>
      </CardContent>
    </Card>
  );
}

function EmptyBlock({
  testId,
  icon,
  title,
  hint,
}: {
  testId: string;
  icon: React.ReactNode;
  title: string;
  hint: string;
}) {
  return (
    <div
      className="flex flex-col items-center justify-center gap-3 py-16 text-muted-foreground"
      data-testid={testId}
    >
      {icon}
      <p className="text-sm font-medium">{title}</p>
      <p className="max-w-sm text-center text-xs">{hint}</p>
    </div>
  );
}

// ─── Agenda tab ──────────────────────────────────────────────────────────────

function AgendaTab() {
  const [status, setStatus] = useState<AppointmentStatus | "">("");

  const appointments = useAppointments(status);
  const requests = useAppointmentRequests();
  const properties = useSchedulingProperties();
  const condominiums = useSchedulingCondominiums();
  const users = useSchedulingUsers();

  const propertyById = useMemo(
    () =>
      new Map((properties.data ?? []).map((p: SchedulingProperty) => [p.id, p])),
    [properties.data],
  );
  const condoById = useMemo(
    () => new Map((condominiums.data ?? []).map((c: Condominium) => [c.id, c])),
    [condominiums.data],
  );
  const userById = useMemo(
    () => new Map((users.data ?? []).map((u: SchedulingUser) => [u.id, u])),
    [users.data],
  );

  const rows = appointments.data ?? [];
  // Skeleton ONLY when there is nothing to show — the seed idiom. Bare
  // `isLoading` is false between retries, which renders a blank panel.
  const showSkeleton =
    appointments.isPending || (appointments.isFetching && rows.length === 0);

  function describe(a: Appointment): string {
    const prop = propertyById.get(a.property_id);
    const condo = condoById.get(a.condominium_id);
    const label = [condo?.name, prop?.code, prop?.unit]
      .filter(Boolean)
      .join(" · ");
    return label || "—";
  }

  const reqRows = requests.data ?? [];
  const reqSkeleton =
    requests.isPending || (requests.isFetching && reqRows.length === 0);

  return (
    <div className="space-y-8">
      {/* ── Compromissos ── */}
      <section className="space-y-3">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="text-sm font-semibold">Compromissos</h2>
            <p className="text-xs text-muted-foreground">
              Visitas agendadas pela equipe de mídia.
            </p>
          </div>
          <div className="w-56">
            <Select
              value={status || "all"}
              onValueChange={(v) =>
                setStatus(v === "all" ? "" : (v as AppointmentStatus))
              }
            >
              <SelectTrigger data-testid="agenda-status-filter">
                <SelectValue placeholder="Todos os status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos os status</SelectItem>
                {(
                  Object.keys(APPOINTMENT_STATUS_LABEL) as AppointmentStatus[]
                ).map((s) => (
                  <SelectItem key={s} value={s}>
                    {APPOINTMENT_STATUS_LABEL[s]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {showSkeleton ? (
          <ListSkeleton testId="agenda-loading" />
        ) : appointments.isError ? (
          <ErrorBlock
            testId="agenda-error"
            message="Erro ao carregar compromissos. Tente novamente."
          />
        ) : rows.length === 0 ? (
          <EmptyBlock
            testId="agenda-empty"
            icon={<CalendarClock className="h-10 w-10 opacity-20" />}
            title="Nenhum compromisso"
            hint="Compromissos confirmados pelo agendador aparecem aqui."
          />
        ) : (
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm" data-testid="agenda-table">
              <thead className="bg-muted/50 text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 text-left">Início</th>
                  <th className="px-3 py-2 text-left">Fim</th>
                  <th className="px-3 py-2 text-left">Local</th>
                  <th className="px-3 py-2 text-left">Equipe</th>
                  <th className="px-3 py-2 text-left">Status</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((a) => (
                  <tr
                    key={a.id}
                    className="border-t"
                    data-testid={`agenda-row-${a.id}`}
                  >
                    <td className="px-3 py-2">{fmtDateTime(a.start_at)}</td>
                    <td className="px-3 py-2">{fmtDateTime(a.end_at)}</td>
                    <td className="px-3 py-2">{describe(a)}</td>
                    <td className="px-3 py-2">
                      {a.media_crew_user_id
                        ? userById.get(a.media_crew_user_id)?.name ?? "—"
                        : "—"}
                    </td>
                    <td className="px-3 py-2">
                      <Badge variant="secondary">
                        {APPOINTMENT_STATUS_LABEL[a.status] ?? a.status}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* ── Solicitações ── */}
      <section className="space-y-3">
        <div>
          <h2 className="text-sm font-semibold">Solicitações</h2>
          <p className="text-xs text-muted-foreground">
            Pedidos de visita ainda em negociação com o corretor.
          </p>
        </div>

        {reqSkeleton ? (
          <ListSkeleton testId="requests-loading" />
        ) : requests.isError ? (
          <ErrorBlock
            testId="requests-error"
            message="Erro ao carregar solicitações. Tente novamente."
          />
        ) : reqRows.length === 0 ? (
          <EmptyBlock
            testId="requests-empty"
            icon={<Inbox className="h-10 w-10 opacity-20" />}
            title="Nenhuma solicitação"
            hint="Pedidos abertos pelo agendador no WhatsApp aparecem aqui."
          />
        ) : (
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm" data-testid="requests-table">
              <thead className="bg-muted/50 text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 text-left">Solicitante</th>
                  <th className="px-3 py-2 text-left">Data pedida</th>
                  <th className="px-3 py-2 text-left">Janela</th>
                  <th className="px-3 py-2 text-left">Status</th>
                  <th className="px-3 py-2 text-left">Observações</th>
                </tr>
              </thead>
              <tbody>
                {reqRows.map((r) => (
                  <tr
                    key={r.id}
                    className="border-t"
                    data-testid={`request-row-${r.id}`}
                  >
                    <td className="px-3 py-2">
                      {userById.get(r.requester_user_id)?.name ?? "—"}
                    </td>
                    <td className="px-3 py-2">{fmtDate(r.requested_date)}</td>
                    <td className="px-3 py-2">
                      {r.requested_time_window ?? "—"}
                    </td>
                    <td className="px-3 py-2">
                      <Badge variant="secondary">
                        {REQUEST_STATUS_LABEL[r.status] ?? r.status}
                      </Badge>
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">
                      {r.notes ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

// ─── Propor tab ──────────────────────────────────────────────────────────────

function ProporTab() {
  const [propertyCode, setPropertyCode] = useState("");
  const [requestedDate, setRequestedDate] = useState("");
  const [timeWindow, setTimeWindow] = useState<"morning" | "afternoon" | "any">(
    "any",
  );
  const [slots, setSlots] = useState<ProposedSlot[] | null>(null);

  const propose = useProposeSlots();
  const properties = useSchedulingProperties();

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSlots(null);
    propose.mutate(
      {
        property_code: propertyCode.trim(),
        requested_date: requestedDate,
        time_window: timeWindow,
      },
      {
        onSuccess: (res) => {
          setSlots(res.slots);
          if (res.slots.length === 0) {
            toast.info("Nenhum horário disponível para essa data.");
          }
        },
        onError: (err: unknown) => {
          toast.error("Não foi possível calcular horários.", {
            description: err instanceof Error ? err.message : undefined,
          });
        },
      },
    );
  }

  const canSubmit =
    propertyCode.trim().length > 0 &&
    requestedDate.length > 0 &&
    !propose.isPending;

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Propor horários</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="space-y-4"
            onSubmit={handleSubmit}
            data-testid="propose-form"
          >
            <div className="space-y-1.5">
              <Label htmlFor="propose-code">Código do imóvel</Label>
              <Input
                id="propose-code"
                list="propose-property-codes"
                value={propertyCode}
                onChange={(e) => setPropertyCode(e.target.value)}
                placeholder="ex.: AP-1203"
                data-testid="propose-code"
              />
              <datalist id="propose-property-codes">
                {(properties.data ?? []).map((p) => (
                  <option key={p.id} value={p.code} />
                ))}
              </datalist>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="propose-date">Data desejada</Label>
              <Input
                id="propose-date"
                type="date"
                value={requestedDate}
                onChange={(e) => setRequestedDate(e.target.value)}
                data-testid="propose-date"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="propose-window">Janela</Label>
              <Select
                value={timeWindow}
                onValueChange={(v) =>
                  setTimeWindow(v as "morning" | "afternoon" | "any")
                }
              >
                <SelectTrigger id="propose-window" data-testid="propose-window">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="any">Qualquer horário</SelectItem>
                  <SelectItem value="morning">Manhã</SelectItem>
                  <SelectItem value="afternoon">Tarde</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <Button
              type="submit"
              disabled={!canSubmit}
              data-testid="propose-submit"
            >
              <Sparkles className="mr-2 h-4 w-4" />
              {propose.isPending ? "Calculando…" : "Calcular horários"}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Horários sugeridos</CardTitle>
        </CardHeader>
        <CardContent>
          {propose.isPending ? (
            <ListSkeleton testId="propose-loading" />
          ) : slots === null ? (
            <p
              className="py-8 text-center text-xs text-muted-foreground"
              data-testid="propose-idle"
            >
              Informe o imóvel e a data para ver as sugestões.
            </p>
          ) : slots.length === 0 ? (
            <EmptyBlock
              testId="propose-empty"
              icon={<CalendarClock className="h-10 w-10 opacity-20" />}
              title="Nenhum horário livre"
              hint="Tente outra data ou amplie a janela para o dia inteiro."
            />
          ) : (
            <ul className="space-y-2" data-testid="propose-results">
              {slots.map((s) => (
                <li
                  key={s.start_at}
                  className="flex items-center justify-between rounded-md border px-3 py-2 text-sm"
                >
                  <div>
                    <p className="font-medium">{fmtDateTime(s.start_at)}</p>
                    <p className="text-xs text-muted-foreground">
                      {s.duration_minutes} min · até {fmtDateTime(s.end_at)}
                    </p>
                  </div>
                  <Badge variant="secondary">
                    score {s.score.toFixed(2)}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ─── Cadastros tab ───────────────────────────────────────────────────────────

function CadastrosTab() {
  const condominiums = useSchedulingCondominiums();

  const condoOptions = (condominiums.data ?? []).map((c) => ({
    value: c.id,
    label: c.name,
  }));

  return (
    <div className="space-y-10" data-testid="cadastros-tab">
      <ResourceManager<Condominium>
        title="Condomínios"
        description="Prédios e endereços onde as visitas acontecem."
        api={api}
        apiPath="/api/scheduling/condominiums"
        singularName="Condomínio"
        canDelete={false}
        emptyMessage="Nenhum condomínio cadastrado ainda."
        columns={[
          { key: "name", header: "Nome" },
          { key: "address", header: "Endereço" },
          {
            key: "active",
            header: "Ativo",
            render: (row) => (row.active ? "Sim" : "Não"),
          },
        ]}
        fields={[
          { name: "name", label: "Nome", required: true },
          { name: "address", label: "Endereço", required: true },
          { name: "latitude", label: "Latitude", type: "number" },
          { name: "longitude", label: "Longitude", type: "number" },
          { name: "notes", label: "Observações", type: "textarea" },
          { name: "active", label: "Ativo", type: "checkbox", defaultValue: true },
        ]}
      />

      <ResourceManager<SchedulingProperty>
        title="Imóveis"
        description="Unidades dentro de um condomínio."
        api={api}
        apiPath="/api/scheduling/properties"
        singularName="Imóvel"
        canDelete={false}
        emptyMessage="Nenhum imóvel cadastrado ainda."
        columns={[
          { key: "code", header: "Código" },
          { key: "unit", header: "Unidade", render: (row) => row.unit ?? "—" },
          {
            key: "active",
            header: "Ativo",
            render: (row) => (row.active ? "Sim" : "Não"),
          },
        ]}
        fields={[
          {
            name: "condominium_id",
            label: "Condomínio",
            type: "select",
            required: true,
            options: condoOptions,
            // The backend's PropertyUpdate has no `condominium_id` — a unit
            // cannot move buildings, so it is set once at creation.
            createOnly: true,
          },
          { name: "code", label: "Código", required: true },
          { name: "unit", label: "Unidade" },
          { name: "address_notes", label: "Complemento", type: "textarea" },
          { name: "active", label: "Ativo", type: "checkbox", defaultValue: true },
        ]}
      />

      <ResourceManager<SchedulingService>
        title="Serviços"
        description="Tipos de visita e sua duração padrão."
        api={api}
        apiPath="/api/scheduling/services"
        singularName="Serviço"
        canDelete={false}
        emptyMessage="Nenhum serviço cadastrado ainda."
        columns={[
          { key: "name", header: "Nome" },
          {
            key: "default_duration_minutes",
            header: "Duração",
            render: (row) => `${row.default_duration_minutes} min`,
          },
          {
            key: "active",
            header: "Ativo",
            render: (row) => (row.active ? "Sim" : "Não"),
          },
        ]}
        fields={[
          { name: "name", label: "Nome", required: true },
          { name: "description", label: "Descrição", type: "textarea" },
          {
            name: "default_duration_minutes",
            label: "Duração padrão (min)",
            type: "number",
            required: true,
            defaultValue: 30,
            min: 1,
            max: 1440,
          },
          { name: "active", label: "Ativo", type: "checkbox", defaultValue: true },
        ]}
      />

      <ResourceManager<SchedulingUser>
        title="Equipe"
        description="Corretores e equipe de mídia que o agendador conhece."
        api={api}
        apiPath="/api/scheduling/users"
        singularName="Pessoa"
        canDelete={false}
        emptyMessage="Nenhuma pessoa cadastrada ainda."
        columns={[
          { key: "name", header: "Nome" },
          {
            key: "role",
            header: "Função",
            render: (row) => ROLE_LABEL[row.role] ?? row.role,
          },
          { key: "phone_number", header: "Telefone" },
          {
            key: "active",
            header: "Ativo",
            render: (row) => (row.active ? "Sim" : "Não"),
          },
        ]}
        fields={[
          { name: "name", label: "Nome", required: true },
          {
            name: "role",
            label: "Função",
            type: "select",
            required: true,
            options: [
              { value: "real_estate_agent", label: "Corretor" },
              { value: "media_crew", label: "Equipe de mídia" },
              { value: "admin", label: "Administrador" },
            ],
          },
          {
            name: "phone_number",
            label: "Telefone",
            required: true,
            help: "Formato E.164, ex.: +5511999998888.",
            // UserUpdate has no `phone_number` — the number is the agendador's
            // identity key, so it is set once at creation.
            createOnly: true,
          },
          { name: "email", label: "E-mail", type: "email" },
          { name: "linked_identity", label: "Identidade WhatsApp" },
          { name: "active", label: "Ativo", type: "checkbox", defaultValue: true },
        ]}
      />
    </div>
  );
}

// ─── Identidades tab ─────────────────────────────────────────────────────────

function IdentidadesTab() {
  const identities = usePendingChatIdentities();
  const users = useSchedulingUsers();
  const resolve = useResolvePendingChatIdentity();

  const [assignee, setAssignee] = useState<Record<string, string>>({});

  const rows = identities.data ?? [];
  const showSkeleton =
    identities.isPending || (identities.isFetching && rows.length === 0);

  function act(row: PendingChatIdentity, status: "resolved" | "rejected") {
    const userId = assignee[row.id];
    if (status === "resolved" && !userId) {
      toast.error("Escolha a pessoa antes de vincular.");
      return;
    }
    resolve.mutate(
      {
        id: row.id,
        status,
        resolvedToUserId: status === "resolved" ? userId : null,
      },
      {
        onSuccess: () =>
          toast.success(
            status === "resolved" ? "Identidade vinculada." : "Identidade recusada.",
          ),
        onError: (err: unknown) =>
          toast.error("Não foi possível concluir.", {
            description: err instanceof Error ? err.message : undefined,
          }),
      },
    );
  }

  return (
    <div className="space-y-3">
      <div>
        <h2 className="text-sm font-semibold">Identidades pendentes</h2>
        <p className="text-xs text-muted-foreground">
          Conversas de WhatsApp que o agendador não conseguiu associar a uma
          pessoa. Vincule para liberar o atendimento automático.
        </p>
      </div>

      {showSkeleton ? (
        <ListSkeleton testId="identidades-loading" />
      ) : identities.isError ? (
        <ErrorBlock
          testId="identidades-error"
          message="Erro ao carregar identidades. Tente novamente."
        />
      ) : rows.length === 0 ? (
        <EmptyBlock
          testId="identidades-empty"
          icon={<UserCheck className="h-10 w-10 opacity-20" />}
          title="Nada pendente"
          hint="Toda conversa recebida foi associada a uma pessoa conhecida."
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm" data-testid="identidades-table">
            <thead className="bg-muted/50 text-xs uppercase text-muted-foreground">
              <tr>
                <th className="px-3 py-2 text-left">Contato</th>
                <th className="px-3 py-2 text-left">Telefone</th>
                <th className="px-3 py-2 text-left">Capturado em</th>
                <th className="px-3 py-2 text-left">Status</th>
                <th className="px-3 py-2 text-left">Vincular a</th>
                <th className="px-3 py-2 text-right">Ações</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.id}
                  className="border-t"
                  data-testid={`identidade-row-${row.id}`}
                >
                  <td className="px-3 py-2">{row.push_name ?? row.chat_id}</td>
                  <td className="px-3 py-2">{row.phone_hint ?? "—"}</td>
                  <td className="px-3 py-2">{fmtDateTime(row.captured_at)}</td>
                  <td className="px-3 py-2">
                    <Badge
                      variant={row.status === "pending" ? "default" : "secondary"}
                    >
                      {row.status}
                    </Badge>
                  </td>
                  <td className="px-3 py-2">
                    <Select
                      value={assignee[row.id] ?? ""}
                      onValueChange={(v) =>
                        setAssignee((prev) => ({ ...prev, [row.id]: v }))
                      }
                      disabled={row.status !== "pending"}
                    >
                      <SelectTrigger
                        className="w-48"
                        data-testid={`identidade-select-${row.id}`}
                      >
                        <SelectValue placeholder="Escolher pessoa" />
                      </SelectTrigger>
                      <SelectContent>
                        {(users.data ?? []).map((u) => (
                          <SelectItem key={u.id} value={u.id}>
                            {u.name} · {ROLE_LABEL[u.role] ?? u.role}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex justify-end gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={row.status !== "pending" || resolve.isPending}
                        onClick={() => act(row, "resolved")}
                        data-testid={`identidade-link-${row.id}`}
                      >
                        <CheckCircle2 className="mr-1 h-3.5 w-3.5" />
                        Vincular
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={row.status !== "pending" || resolve.isPending}
                        onClick={() => act(row, "rejected")}
                        data-testid={`identidade-reject-${row.id}`}
                      >
                        <XCircle className="mr-1 h-3.5 w-3.5" />
                        Recusar
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function Agendamentos() {
  return (
    <div className="flex flex-col gap-6 p-6" data-testid="agendamentos-page">
      <header>
        <h1 className="text-lg font-semibold">Agendamentos</h1>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Agenda de visitas, cadastros do agendador e identidades pendentes.
        </p>
      </header>

      <Tabs defaultValue="agenda" className="w-full">
        <TabsList className="grid w-full grid-cols-4 sm:max-w-2xl">
          <TabsTrigger value="agenda">Agenda</TabsTrigger>
          <TabsTrigger value="propor">Propor</TabsTrigger>
          <TabsTrigger value="cadastros">Cadastros</TabsTrigger>
          <TabsTrigger value="identidades">Identidades</TabsTrigger>
        </TabsList>

        <TabsContent value="agenda" className="mt-6">
          <AgendaTab />
        </TabsContent>
        <TabsContent value="propor" className="mt-6">
          <ProporTab />
        </TabsContent>
        <TabsContent value="cadastros" className="mt-6">
          <CadastrosTab />
        </TabsContent>
        <TabsContent value="identidades" className="mt-6">
          <IdentidadesTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
