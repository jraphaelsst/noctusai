/**
 * Email Marketing · Campanhas — the campaign lifecycle surface.
 *
 * Covers every campaign route the module exposes:
 *   GET|POST   /api/email-marketing/campaigns
 *   PATCH|DELETE /api/email-marketing/campaigns/{id}
 *   POST       /campaigns/{id}/schedule · /send · /pause · /cancel
 *   GET        /analytics/campaigns/{id}          (per-campaign numbers)
 *   GET|POST   /ai/campaigns/{id}/debrief[/send]  (post-send AI debrief)
 *   POST       /ai/subjects                       (subject-line assist)
 *
 * Lifecycle actions are gated on `status` the same way the backend gates them,
 * so the UI never offers a button the API will refuse.
 *
 * Route: /email/campanhas (`email_campanhas_noc` status_pagina, migration 085).
 */
import { useMemo, useState } from "react";
import { toast } from "sonner";
import {
  AlertCircle,
  Ban,
  BarChart3,
  CalendarClock,
  Mail,
  Pause,
  Plus,
  Send,
  Sparkles,
  Trash2,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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

import {
  useEmAi,
  useEmCampaignAnalytics,
  useEmCampaignMutations,
  useEmCampaigns,
  useEmLists,
  useEmTemplates,
  type CampaignStatus,
  type EmCampaign,
} from "@/hooks/useEmailMarketing";

const STATUS_LABEL: Record<CampaignStatus, string> = {
  rascunho: "Rascunho",
  agendada: "Agendada",
  enviando: "Enviando",
  enviada: "Enviada",
  pausada: "Pausada",
  cancelada: "Cancelada",
};

/** Mirrors the backend's own status gating — never offer a refused action. */
const CAN = {
  edit: (s: CampaignStatus) => s === "rascunho" || s === "agendada",
  schedule: (s: CampaignStatus) => s === "rascunho" || s === "agendada",
  send: (s: CampaignStatus) => s === "rascunho" || s === "agendada",
  pause: (s: CampaignStatus) => s === "enviando",
  cancel: (s: CampaignStatus) =>
    s === "rascunho" || s === "agendada" || s === "pausada",
  remove: (s: CampaignStatus) => s === "rascunho" || s === "cancelada",
  debrief: (s: CampaignStatus) => s === "enviada",
};

function fmtDateTime(v: string | null): string {
  if (!v) return "—";
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? v : d.toLocaleString("pt-BR");
}

// ─── Create / edit dialog ────────────────────────────────────────────────────

interface FormState {
  nome: string;
  template_id: string;
  list_id: string;
  assunto_override: string;
  remetente_nome: string;
  remetente_email: string;
}

const emptyForm = (): FormState => ({
  nome: "",
  template_id: "",
  list_id: "",
  assunto_override: "",
  remetente_nome: "",
  remetente_email: "",
});

function CampaignDialog({
  open,
  editing,
  onClose,
}: {
  open: boolean;
  editing: EmCampaign | null;
  onClose: () => void;
}) {
  const templates = useEmTemplates();
  const lists = useEmLists();
  const { create, update } = useEmCampaignMutations();
  const ai = useEmAi();

  const [form, setForm] = useState<FormState>(
    editing
      ? {
          nome: editing.nome,
          template_id: editing.template_id ?? "",
          list_id: editing.list_id ?? "",
          assunto_override: editing.assunto_override ?? "",
          remetente_nome: editing.remetente_nome ?? "",
          remetente_email: editing.remetente_email ?? "",
        }
      : emptyForm(),
  );
  const [suggestions, setSuggestions] = useState<string[]>([]);

  const set = (k: keyof FormState) => (v: string) =>
    setForm((prev) => ({ ...prev, [k]: v }));

  const valid =
    form.nome.trim().length > 0 &&
    form.template_id.length > 0 &&
    form.list_id.length > 0;

  function suggestSubjects() {
    const summary = form.assunto_override.trim() || form.nome.trim();
    if (!summary) {
      toast.error("Escreva o nome da campanha antes de pedir sugestões.");
      return;
    }
    ai.subjects.mutate(summary, {
      onSuccess: (res: any) => {
        const list: string[] = res?.data?.subjects ?? res?.subjects ?? [];
        setSuggestions(list);
        if (list.length === 0) toast.info("A IA não retornou sugestões.");
      },
      onError: () => toast.error("Não foi possível gerar sugestões."),
    });
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const payload = {
      nome: form.nome.trim(),
      template_id: form.template_id,
      list_id: form.list_id,
      assunto_override: form.assunto_override.trim() || null,
      remetente_nome: form.remetente_nome.trim() || null,
      remetente_email: form.remetente_email.trim() || null,
    };
    const done = (msg: string) => {
      toast.success(msg);
      onClose();
    };
    if (editing) {
      update.mutate(
        { id: editing.id, body: payload },
        {
          onSuccess: () => done("Campanha atualizada."),
          onError: () => toast.error("Erro ao atualizar campanha."),
        },
      );
    } else {
      create.mutate(payload, {
        onSuccess: () => done("Campanha criada."),
        onError: () => toast.error("Erro ao criar campanha."),
      });
    }
  }

  if (!open) return null;

  return (
    <Dialog open={open} onOpenChange={(o: boolean) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {editing ? "Editar campanha" : "Nova campanha"}
          </DialogTitle>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={submit}
          data-testid="campanha-form"
        >
          <div className="space-y-1.5">
            <Label htmlFor="c-nome">Nome</Label>
            <Input
              id="c-nome"
              value={form.nome}
              onChange={(e) => set("nome")(e.target.value)}
              data-testid="campanha-nome"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="c-template">Template</Label>
            <Select value={form.template_id} onValueChange={set("template_id")}>
              <SelectTrigger id="c-template" data-testid="campanha-template">
                <SelectValue placeholder="Escolha um template" />
              </SelectTrigger>
              <SelectContent>
                {(templates.data ?? []).map((t) => (
                  <SelectItem key={t.id} value={t.id}>
                    {t.nome}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="c-list">Lista</Label>
            <Select value={form.list_id} onValueChange={set("list_id")}>
              <SelectTrigger id="c-list" data-testid="campanha-lista">
                <SelectValue placeholder="Escolha uma lista" />
              </SelectTrigger>
              <SelectContent>
                {(lists.data ?? []).map((l) => (
                  <SelectItem key={l.id} value={l.id}>
                    {l.nome} ({l.contact_count})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label htmlFor="c-assunto">Assunto (opcional)</Label>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={suggestSubjects}
                disabled={ai.subjects.isPending}
                data-testid="campanha-ai-subjects"
              >
                <Sparkles className="mr-1 h-3.5 w-3.5" />
                {ai.subjects.isPending ? "Gerando…" : "Sugerir"}
              </Button>
            </div>
            <Input
              id="c-assunto"
              value={form.assunto_override}
              onChange={(e) => set("assunto_override")(e.target.value)}
              data-testid="campanha-assunto"
            />
            {suggestions.length > 0 && (
              <ul className="space-y-1 pt-1" data-testid="campanha-ai-suggestions">
                {suggestions.map((s) => (
                  <li key={s}>
                    <button
                      type="button"
                      className="w-full rounded border px-2 py-1 text-left text-xs hover:bg-muted"
                      onClick={() => set("assunto_override")(s)}
                    >
                      {s}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="c-rnome">Remetente</Label>
              <Input
                id="c-rnome"
                value={form.remetente_nome}
                onChange={(e) => set("remetente_nome")(e.target.value)}
                data-testid="campanha-remetente-nome"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="c-remail">E-mail do remetente</Label>
              <Input
                id="c-remail"
                type="email"
                value={form.remetente_email}
                onChange={(e) => set("remetente_email")(e.target.value)}
                data-testid="campanha-remetente-email"
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              type="submit"
              disabled={!valid || create.isPending || update.isPending}
              data-testid="campanha-submit"
            >
              {editing ? "Salvar" : "Criar campanha"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ─── Analytics drawer ────────────────────────────────────────────────────────

function AnalyticsPanel({ campaignId }: { campaignId: string }) {
  const { data, isPending, isError } = useEmCampaignAnalytics(campaignId);
  if (isPending) return <Skeleton className="h-24 w-full" />;
  if (isError)
    return (
      <p className="text-xs text-destructive" data-testid="campanha-analytics-error">
        Erro ao carregar métricas desta campanha.
      </p>
    );
  if (!data)
    return (
      <p className="text-xs text-muted-foreground" data-testid="campanha-analytics-empty">
        Sem métricas para esta campanha ainda.
      </p>
    );
  return (
    <pre
      className="max-h-64 overflow-auto rounded bg-muted p-3 text-xs"
      data-testid="campanha-analytics"
    >
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function EmailCampanhasNoc() {
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<EmCampaign | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [scheduleFor, setScheduleFor] = useState<EmCampaign | null>(null);
  const [scheduleAt, setScheduleAt] = useState("");

  const { data, isPending, isFetching, isError } = useEmCampaigns(
    statusFilter || undefined,
  );
  const { remove, schedule, send, pause, cancel } = useEmCampaignMutations();
  const ai = useEmAi();
  const templates = useEmTemplates();
  const lists = useEmLists();

  const rows = data ?? [];
  const showSkeleton = isPending || (isFetching && rows.length === 0);

  const templateName = useMemo(
    () => new Map((templates.data ?? []).map((t) => [t.id, t.nome])),
    [templates.data],
  );
  const listName = useMemo(
    () => new Map((lists.data ?? []).map((l) => [l.id, l.nome])),
    [lists.data],
  );

  function act(
    label: string,
    fn: { mutate: (v: any, o?: any) => void },
    arg: any,
  ) {
    fn.mutate(arg, {
      onSuccess: () => toast.success(label),
      onError: (err: unknown) =>
        toast.error(`Não foi possível concluir: ${label.toLowerCase()}`, {
          description: err instanceof Error ? err.message : undefined,
        }),
    });
  }

  function confirmSchedule() {
    if (!scheduleFor || !scheduleAt) return;
    schedule.mutate(
      { id: scheduleFor.id, scheduledAt: new Date(scheduleAt).toISOString() },
      {
        onSuccess: () => {
          toast.success("Campanha agendada.");
          setScheduleFor(null);
          setScheduleAt("");
        },
        onError: () => toast.error("Erro ao agendar campanha."),
      },
    );
  }

  return (
    <div className="flex flex-col gap-6 p-6" data-testid="email-campanhas-page">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold">Campanhas</h1>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Envios do motor próprio — rascunho, agendamento, disparo e pausa.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-48">
            <Select
              value={statusFilter || "all"}
              onValueChange={(v) => setStatusFilter(v === "all" ? "" : v)}
            >
              <SelectTrigger data-testid="campanhas-status-filter">
                <SelectValue placeholder="Todos os status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos os status</SelectItem>
                {(Object.keys(STATUS_LABEL) as CampaignStatus[]).map((s) => (
                  <SelectItem key={s} value={s}>
                    {STATUS_LABEL[s]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button
            onClick={() => {
              setEditing(null);
              setDialogOpen(true);
            }}
            data-testid="campanhas-nova"
          >
            <Plus className="mr-2 h-4 w-4" />
            Nova campanha
          </Button>
        </div>
      </div>

      {showSkeleton ? (
        <div className="space-y-2" data-testid="campanhas-loading">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : isError ? (
        <Card className="border-destructive" data-testid="campanhas-error">
          <CardContent className="flex items-center gap-3 pt-6">
            <AlertCircle className="h-5 w-5 text-destructive" />
            <p className="text-sm text-destructive">
              Erro ao carregar campanhas. Tente novamente.
            </p>
          </CardContent>
        </Card>
      ) : rows.length === 0 ? (
        <div
          className="flex flex-col items-center justify-center gap-3 py-16 text-muted-foreground"
          data-testid="campanhas-empty"
        >
          <Mail className="h-10 w-10 opacity-20" />
          <p className="text-sm font-medium">Nenhuma campanha</p>
          <p className="max-w-sm text-center text-xs">
            Crie uma campanha escolhendo um template e uma lista de contatos.
          </p>
        </div>
      ) : (
        <div className="space-y-2" data-testid="campanhas-list">
          {rows.map((c) => (
            <Card key={c.id} data-testid={`campanha-row-${c.id}`}>
              <CardContent className="pt-6">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="truncate font-medium">{c.nome}</p>
                      <Badge variant="secondary">
                        {STATUS_LABEL[c.status] ?? c.status}
                      </Badge>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {templateName.get(c.template_id ?? "") ?? "sem template"} ·{" "}
                      {listName.get(c.list_id ?? "") ?? "sem lista"} ·{" "}
                      {c.total_sent}/{c.total_recipients} enviados
                      {c.scheduled_at
                        ? ` · agendada para ${fmtDateTime(c.scheduled_at)}`
                        : ""}
                    </p>
                  </div>

                  <div className="flex flex-wrap items-center gap-1">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() =>
                        setExpanded((prev) => (prev === c.id ? null : c.id))
                      }
                      data-testid={`campanha-metrics-${c.id}`}
                    >
                      <BarChart3 className="mr-1 h-3.5 w-3.5" />
                      Métricas
                    </Button>

                    {CAN.edit(c.status) && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          setEditing(c);
                          setDialogOpen(true);
                        }}
                        data-testid={`campanha-edit-${c.id}`}
                      >
                        Editar
                      </Button>
                    )}
                    {CAN.schedule(c.status) && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setScheduleFor(c)}
                        data-testid={`campanha-schedule-${c.id}`}
                      >
                        <CalendarClock className="mr-1 h-3.5 w-3.5" />
                        Agendar
                      </Button>
                    )}
                    {CAN.send(c.status) && (
                      <Button
                        size="sm"
                        onClick={() => act("Campanha enviada.", send, c.id)}
                        data-testid={`campanha-send-${c.id}`}
                      >
                        <Send className="mr-1 h-3.5 w-3.5" />
                        Enviar
                      </Button>
                    )}
                    {CAN.pause(c.status) && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => act("Campanha pausada.", pause, c.id)}
                        data-testid={`campanha-pause-${c.id}`}
                      >
                        <Pause className="mr-1 h-3.5 w-3.5" />
                        Pausar
                      </Button>
                    )}
                    {CAN.cancel(c.status) && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => act("Campanha cancelada.", cancel, c.id)}
                        data-testid={`campanha-cancel-${c.id}`}
                      >
                        <Ban className="mr-1 h-3.5 w-3.5" />
                        Cancelar
                      </Button>
                    )}
                    {CAN.debrief(c.status) && (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={ai.sendDebrief.isPending}
                        onClick={() =>
                          act("Debrief enviado.", ai.sendDebrief, c.id)
                        }
                        data-testid={`campanha-debrief-${c.id}`}
                      >
                        <Sparkles className="mr-1 h-3.5 w-3.5" />
                        Debrief
                      </Button>
                    )}
                    {CAN.remove(c.status) && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => act("Campanha removida.", remove, c.id)}
                        data-testid={`campanha-delete-${c.id}`}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    )}
                  </div>
                </div>

                {expanded === c.id && (
                  <div className="mt-4">
                    <AnalyticsPanel campaignId={c.id} />
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {dialogOpen && (
        <CampaignDialog
          open={dialogOpen}
          editing={editing}
          onClose={() => {
            setDialogOpen(false);
            setEditing(null);
          }}
        />
      )}

      {/* Schedule dialog */}
      <Dialog
        open={!!scheduleFor}
        onOpenChange={(o: boolean) => !o && setScheduleFor(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Agendar campanha</DialogTitle>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="sched-at">Data e hora</Label>
            <Input
              id="sched-at"
              type="datetime-local"
              value={scheduleAt}
              onChange={(e) => setScheduleAt(e.target.value)}
              data-testid="campanha-schedule-at"
            />
          </div>
          <DialogFooter>
            <Button
              onClick={confirmSchedule}
              disabled={!scheduleAt || schedule.isPending}
              data-testid="campanha-schedule-confirm"
            >
              Agendar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
