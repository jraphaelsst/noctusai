/**
 * Email Marketing · Automações — trigger-driven sequences.
 *
 *   GET|POST     /api/email-marketing/automations
 *   GET|PATCH|DELETE /automations/{id}
 *   POST         /automations/{id}/activate · /pause · /enroll
 *   GET|POST     /automations/{id}/steps
 *   PATCH|DELETE /automations/{id}/steps/{step_id}
 *   POST         /automations/{id}/steps/reorder
 *   GET          /automations/{id}/enrollments
 *
 * The list is the `<ResourceManager/>` organ; selecting a row opens the step
 * editor (add / reorder / remove) and the enrollment panel — neither of which
 * the organ has a notion of.
 *
 * Route: /email/automacoes (`email_automacoes_noc` status_pagina, migration 085).
 */
import { useState } from "react";
import { toast } from "sonner";
import {
  AlertCircle,
  ArrowDown,
  ArrowUp,
  Pause,
  Play,
  Plus,
  Trash2,
  UserPlus,
  Workflow,
} from "lucide-react";

import { ResourceManager } from "@noctusai/lib/components";
import { api } from "@/lib/api";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

import {
  useEmAutomationEnrollments,
  useEmAutomationMutations,
  useEmAutomationSteps,
  useEmAutomations,
  useEmContacts,
  type EmAutomation,
} from "@/hooks/useEmailMarketing";

const TRIGGER_OPTIONS = [
  { value: "contact_added", label: "Contato criado" },
  { value: "tag_added", label: "Tag adicionada" },
  { value: "list_joined", label: "Entrou numa lista" },
  { value: "form_submitted", label: "Formulário enviado" },
  { value: "manual", label: "Manual" },
  { value: "webhook", label: "Webhook" },
];

const STEP_OPTIONS = [
  { value: "send_email", label: "Enviar e-mail" },
  { value: "wait", label: "Esperar" },
  { value: "condition", label: "Condição" },
  { value: "add_tag", label: "Adicionar tag" },
  { value: "remove_tag", label: "Remover tag" },
  { value: "move_to_list", label: "Mover para lista" },
  { value: "webhook", label: "Webhook" },
];

const STATUS_LABEL: Record<string, string> = {
  rascunho: "Rascunho",
  ativa: "Ativa",
  pausada: "Pausada",
};

const stepLabel = (tipo: string) =>
  STEP_OPTIONS.find((o) => o.value === tipo)?.label ?? tipo;

// ─── Step editor ─────────────────────────────────────────────────────────────

function StepsPanel({ automation }: { automation: EmAutomation }) {
  const steps = useEmAutomationSteps(automation.id);
  const { addStep, removeStep, reorderSteps } = useEmAutomationMutations();
  const [tipo, setTipo] = useState("send_email");

  const rows = [...(steps.data ?? [])].sort((a, b) => a.posicao - b.posicao);
  const showSkeleton =
    steps.isPending || (steps.isFetching && rows.length === 0);

  function move(index: number, delta: number) {
    const next = [...rows];
    const target = index + delta;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    reorderSteps.mutate(
      { id: automation.id, stepIds: next.map((s) => s.id) },
      {
        onSuccess: () => {
          toast.success("Ordem atualizada.");
          steps.refetch();
        },
        onError: () => toast.error("Erro ao reordenar."),
      },
    );
  }

  return (
    <Card data-testid="automacao-steps">
      <CardHeader>
        <CardTitle className="text-base">Passos · {automation.nome}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex gap-2">
          <Select value={tipo} onValueChange={setTipo}>
            <SelectTrigger data-testid="step-tipo">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {STEP_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            onClick={() =>
              addStep.mutate(
                { id: automation.id, tipo, config: {} },
                {
                  onSuccess: () => {
                    toast.success("Passo adicionado.");
                    steps.refetch();
                  },
                  onError: () => toast.error("Erro ao adicionar passo."),
                },
              )
            }
            disabled={addStep.isPending}
            data-testid="step-add"
          >
            <Plus className="h-4 w-4" />
          </Button>
        </div>

        {showSkeleton ? (
          <div className="space-y-2" data-testid="steps-loading">
            {[1, 2].map((i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : steps.isError ? (
          <div
            className="flex items-center gap-2 text-sm text-destructive"
            data-testid="steps-error"
          >
            <AlertCircle className="h-4 w-4" />
            Erro ao carregar os passos.
          </div>
        ) : rows.length === 0 ? (
          <p
            className="py-6 text-center text-xs text-muted-foreground"
            data-testid="steps-empty"
          >
            Nenhum passo ainda — adicione o primeiro acima.
          </p>
        ) : (
          <ol className="divide-y rounded-md border" data-testid="steps-rows">
            {rows.map((s, i) => (
              <li
                key={s.id}
                className="flex items-center justify-between px-3 py-2 text-sm"
                data-testid={`step-row-${s.id}`}
              >
                <span>
                  <span className="mr-2 text-xs text-muted-foreground">
                    {i + 1}.
                  </span>
                  {stepLabel(s.tipo)}
                </span>
                <span className="flex gap-1">
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={i === 0}
                    onClick={() => move(i, -1)}
                    data-testid={`step-up-${s.id}`}
                  >
                    <ArrowUp className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={i === rows.length - 1}
                    onClick={() => move(i, 1)}
                    data-testid={`step-down-${s.id}`}
                  >
                    <ArrowDown className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() =>
                      removeStep.mutate(
                        { id: automation.id, stepId: s.id },
                        {
                          onSuccess: () => {
                            toast.success("Passo removido.");
                            steps.refetch();
                          },
                          onError: () => toast.error("Erro ao remover passo."),
                        },
                      )
                    }
                    data-testid={`step-remove-${s.id}`}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </span>
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Enrollment panel ────────────────────────────────────────────────────────

function EnrollPanel({ automation }: { automation: EmAutomation }) {
  const enrollments = useEmAutomationEnrollments(automation.id);
  const contacts = useEmContacts();
  const { enroll } = useEmAutomationMutations();
  const [pick, setPick] = useState("");

  const rows = enrollments.data ?? [];
  const showSkeleton =
    enrollments.isPending || (enrollments.isFetching && rows.length === 0);
  const emailById = new Map((contacts.data ?? []).map((c) => [c.id, c.email]));

  return (
    <Card data-testid="automacao-enrollments">
      <CardHeader>
        <CardTitle className="text-base">Inscritos</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex gap-2">
          <Select value={pick} onValueChange={setPick}>
            <SelectTrigger data-testid="enroll-pick">
              <SelectValue placeholder="Escolha um contato" />
            </SelectTrigger>
            <SelectContent>
              {(contacts.data ?? []).map((c) => (
                <SelectItem key={c.id} value={c.id}>
                  {c.email}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            onClick={() =>
              enroll.mutate(
                { id: automation.id, contactIds: [pick] },
                {
                  onSuccess: () => {
                    toast.success("Contato inscrito.");
                    setPick("");
                    enrollments.refetch();
                  },
                  onError: () => toast.error("Erro ao inscrever contato."),
                },
              )
            }
            disabled={!pick || enroll.isPending}
            data-testid="enroll-add"
          >
            <UserPlus className="h-4 w-4" />
          </Button>
        </div>

        {showSkeleton ? (
          <div className="space-y-2" data-testid="enrollments-loading">
            {[1, 2].map((i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : enrollments.isError ? (
          <div
            className="flex items-center gap-2 text-sm text-destructive"
            data-testid="enrollments-error"
          >
            <AlertCircle className="h-4 w-4" />
            Erro ao carregar inscritos.
          </div>
        ) : rows.length === 0 ? (
          <p
            className="py-6 text-center text-xs text-muted-foreground"
            data-testid="enrollments-empty"
          >
            Nenhum contato inscrito nesta automação.
          </p>
        ) : (
          <ul className="divide-y rounded-md border" data-testid="enrollments-rows">
            {rows.map((e) => (
              <li
                key={e.id}
                className="flex items-center justify-between px-3 py-2 text-sm"
                data-testid={`enrollment-row-${e.id}`}
              >
                <span>{emailById.get(e.contact_id) ?? e.contact_id}</span>
                <Badge variant="secondary">{e.status}</Badge>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function EmailAutomacoes() {
  const automations = useEmAutomations();
  const { activate, pause } = useEmAutomationMutations();
  const [selectedId, setSelectedId] = useState<string>("");

  const rows = automations.data ?? [];
  const selected = rows.find((a) => a.id === selectedId) ?? null;

  return (
    <div className="flex flex-col gap-8 p-6" data-testid="email-automacoes-page">
      <ResourceManager<EmAutomation>
        title="Automações"
        description="Sequências disparadas por eventos na base de contatos."
        api={api}
        apiPath="/api/email-marketing/automations"
        singularName="Automação"
        emptyMessage="Nenhuma automação ainda."
        onMutate={() => automations.refetch()}
        columns={[
          { key: "nome", header: "Nome" },
          {
            key: "trigger_type",
            header: "Gatilho",
            render: (r) =>
              TRIGGER_OPTIONS.find((o) => o.value === r.trigger_type)?.label ??
              r.trigger_type,
          },
          {
            key: "status",
            header: "Status",
            render: (r) => STATUS_LABEL[r.status] ?? r.status,
          },
        ]}
        fields={[
          { name: "nome", label: "Nome", required: true },
          { name: "descricao", label: "Descrição", type: "textarea" },
          {
            name: "trigger_type",
            label: "Gatilho",
            type: "select",
            required: true,
            defaultValue: "contact_added",
            options: TRIGGER_OPTIONS,
          },
        ]}
        rowActions={(row, reload) => (
          <span className="flex gap-1">
            <button
              type="button"
              className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs text-muted-foreground hover:bg-muted"
              onClick={() => setSelectedId(row.id)}
              data-testid={`automacao-open-${row.id}`}
            >
              <Workflow className="h-3.5 w-3.5" />
              Passos
            </button>
            {row.status !== "ativa" ? (
              <button
                type="button"
                className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs text-muted-foreground hover:bg-muted"
                data-testid={`automacao-activate-${row.id}`}
                onClick={() =>
                  activate.mutate(row.id, {
                    onSuccess: () => {
                      toast.success("Automação ativada.");
                      reload();
                    },
                    onError: () => toast.error("Erro ao ativar."),
                  })
                }
              >
                <Play className="h-3.5 w-3.5" />
                Ativar
              </button>
            ) : (
              <button
                type="button"
                className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs text-muted-foreground hover:bg-muted"
                data-testid={`automacao-pause-${row.id}`}
                onClick={() =>
                  pause.mutate(row.id, {
                    onSuccess: () => {
                      toast.success("Automação pausada.");
                      reload();
                    },
                    onError: () => toast.error("Erro ao pausar."),
                  })
                }
              >
                <Pause className="h-3.5 w-3.5" />
                Pausar
              </button>
            )}
          </span>
        )}
      />

      {selected ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <StepsPanel automation={selected} />
          <EnrollPanel automation={selected} />
        </div>
      ) : (
        <p
          className="text-center text-xs text-muted-foreground"
          data-testid="automacoes-none-selected"
        >
          Escolha "Passos" numa automação para editar a sequência e os inscritos.
        </p>
      )}
    </div>
  );
}
