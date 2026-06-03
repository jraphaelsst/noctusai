/**
 * Automacao — WhatsApp flow automation page for Orbity.
 *
 * Sections (tabs):
 *   1. Fluxos     — flows list (name, trigger_type, active toggle); create/edit a flow
 *   2. Passos     — expandable steps editor per selected flow (ordered list, step_type + config)
 *   3. Execucoes  — executions panel (status, current step, lead); "Run due" button
 *
 * Every section ships all four states: loading / empty / error / success.
 *
 * Nav: registered under route key "automacao" — requires a status_pagina
 * row with page_key = "automacao" (see return note).
 */
import { useState } from "react";
import {
  Zap,
  Plus,
  Pencil,
  Trash2,
  Loader2,
  AlertCircle,
  FileText,
  Play,
  ChevronDown,
  ChevronUp,
  X,
  RefreshCw,
  XCircle,
  CheckCircle2,
  Clock,
  AlertTriangle,
  ArrowRight,
} from "lucide-react";
import {
  useFlows,
  useCreateFlow,
  useUpdateFlow,
  useDeleteFlow,
  useSteps,
  useCreateStep,
  useUpdateStep,
  useDeleteStep,
  useTriggerFlow,
  useExecutions,
  useCancelExecution,
  useRunDue,
  type Flow,
  type Step,
  type Execution,
  type TriggerType,
  type StepType,
  type FlowCreate,
  type StepCreate,
} from "@/hooks/useAutomacao";

// ---------------------------------------------------------------------------
// Vocabulary maps
// ---------------------------------------------------------------------------

const TRIGGER_LABELS: Record<TriggerType, string> = {
  lead_created: "Lead criado",
  pipeline_stage_entered: "Etapa do funil atingida",
  lead_idle: "Lead inativo",
  whatsapp_message_received: "Mensagem WhatsApp recebida",
  keyword_received: "Palavra-chave recebida",
  tag_added: "Tag adicionada",
  owner_changed: "Responsavel alterado",
  task_created: "Tarefa criada",
  task_completed: "Tarefa concluida",
  meeting_created: "Reuniao criada",
  proposal_sent: "Proposta enviada",
  client_created: "Cliente criado",
  lead_status_changed: "Status do lead alterado",
  manual: "Manual",
};

const STEP_TYPE_LABELS: Record<StepType, string> = {
  send_message: "Enviar mensagem",
  send_whatsapp_media: "Enviar midia WhatsApp",
  wait: "Aguardar",
  condition: "Condicao",
  action: "Acao",
  branch: "Ramificacao",
  end: "Fim",
};

const STEP_TYPE_COLORS: Record<StepType, string> = {
  send_message:
    "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
  send_whatsapp_media:
    "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  wait: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400",
  condition:
    "bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400",
  action:
    "bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400",
  branch: "bg-pink-100 text-pink-800 dark:bg-pink-900/30 dark:text-pink-400",
  end: "bg-gray-100 text-gray-600 dark:bg-gray-900/30 dark:text-gray-400",
};

const EXECUTION_STATUS_LABELS: Record<string, string> = {
  running: "Executando",
  done: "Concluida",
  canceled: "Cancelada",
  failed: "Falhou",
};

const EXECUTION_STATUS_COLORS: Record<string, string> = {
  running:
    "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
  done: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  canceled:
    "bg-gray-100 text-gray-600 dark:bg-gray-900/30 dark:text-gray-400",
  failed:
    "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
};

const EXECUTION_STATUS_ICONS: Record<string, React.ElementType> = {
  running: Loader2,
  done: CheckCircle2,
  canceled: XCircle,
  failed: AlertTriangle,
};

// ---------------------------------------------------------------------------
// Shared state renderers
// ---------------------------------------------------------------------------

function LoadingState({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3">
      <Loader2 className="h-7 w-7 animate-spin text-primary" />
      <p className="text-sm text-muted-foreground">{label}</p>
    </div>
  );
}

function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3 text-destructive">
      <AlertCircle className="h-7 w-7" />
      <p className="text-sm font-medium">Erro ao carregar dados</p>
      <p className="text-xs text-muted-foreground max-w-sm text-center">
        {message}
      </p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-1 rounded-md border border-destructive/30 bg-destructive/10 px-4 py-1.5 text-xs font-medium text-destructive hover:bg-destructive/20 transition-colors"
        >
          Tentar novamente
        </button>
      )}
    </div>
  );
}

function EmptyState({
  label,
  onAdd,
}: {
  label: string;
  onAdd?: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3">
      <FileText className="h-8 w-8 text-muted-foreground/40" />
      <p className="text-sm text-muted-foreground">{label}</p>
      {onAdd && (
        <button
          onClick={onAdd}
          className="mt-1 inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          <Plus className="h-3.5 w-3.5" />
          Adicionar
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Flow dialog (create / edit)
// ---------------------------------------------------------------------------

function FlowDialog({
  open,
  editing,
  onClose,
}: {
  open: boolean;
  editing: Flow | null;
  onClose: () => void;
}) {
  const createMut = useCreateFlow();
  const updateMut = useUpdateFlow();

  const [form, setForm] = useState<FlowCreate>({
    name: editing?.name ?? "",
    trigger_type: editing?.trigger_type ?? "manual",
    active: editing?.active ?? true,
  });

  if (!open) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (editing) {
      await updateMut.mutateAsync({ id: editing.id, ...form });
    } else {
      await createMut.mutateAsync(form);
    }
    onClose();
  }

  const isPending = createMut.isPending || updateMut.isPending;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className="w-full max-w-[calc(100vw-2rem)] sm:max-w-lg rounded-lg border border-border bg-card p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-foreground">
            {editing ? "Editar fluxo" : "Novo fluxo de automacao"}
          </h2>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">
              Nome *
            </label>
            <input
              type="text"
              required
              value={form.name}
              onChange={(e) =>
                setForm((f) => ({ ...f, name: e.target.value }))
              }
              placeholder="Ex.: Boas-vindas para novos leads"
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">
              Gatilho *
            </label>
            <select
              value={form.trigger_type}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  trigger_type: e.target.value as TriggerType,
                }))
              }
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {(Object.keys(TRIGGER_LABELS) as TriggerType[]).map((t) => (
                <option key={t} value={t}>
                  {TRIGGER_LABELS[t]}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="active"
              checked={form.active ?? true}
              onChange={(e) =>
                setForm((f) => ({ ...f, active: e.target.checked }))
              }
              className="h-4 w-4 rounded border-input accent-primary"
            />
            <label
              htmlFor="active"
              className="text-sm font-medium text-foreground"
            >
              Fluxo ativo
            </label>
          </div>
          <div className="flex justify-end gap-3 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-muted transition-colors"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={isPending}
              className="inline-flex items-center gap-2 rounded-md bg-primary px-5 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Salvando...
                </>
              ) : editing ? (
                "Salvar alteracoes"
              ) : (
                "Criar fluxo"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step dialog (create / edit)
// ---------------------------------------------------------------------------

const STEP_CONFIG_PLACEHOLDERS: Partial<Record<StepType, string>> = {
  send_message: '{"template": "Ola {{lead_name}}, bem-vindo!"}',
  send_whatsapp_media:
    '{"template": "Confira nosso material", "media_url": "https://..."}',
  wait: '{"duration_minutes": 60}',
  condition: '{"field": "status", "operator": "eq", "value": "new"}',
  action: '{"action_type": "add_tag", "tag": "interessado"}',
  branch: '{"branches": []}',
  end: "{}",
};

function StepDialog({
  open,
  flowId,
  editing,
  nextOrd,
  onClose,
}: {
  open: boolean;
  flowId: string;
  editing: Step | null;
  nextOrd: number;
  onClose: () => void;
}) {
  const createMut = useCreateStep(flowId);
  const updateMut = useUpdateStep();

  const [stepType, setStepType] = useState<StepType>(
    editing?.step_type ?? "send_message",
  );
  const [configStr, setConfigStr] = useState<string>(
    editing ? JSON.stringify(editing.config, null, 2) : "",
  );
  const [configError, setConfigError] = useState<string>("");

  if (!open) return null;

  function parseConfig(): Record<string, unknown> | null {
    const raw = configStr.trim() || "{}";
    try {
      return JSON.parse(raw);
    } catch {
      setConfigError("JSON invalido");
      return null;
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setConfigError("");
    const config = parseConfig();
    if (config === null) return;

    if (editing) {
      await updateMut.mutateAsync({
        stepId: editing.id,
        flowId,
        step_type: stepType,
        config,
      });
    } else {
      const payload: StepCreate = {
        ord: nextOrd,
        step_type: stepType,
        config,
      };
      await createMut.mutateAsync(payload);
    }
    onClose();
  }

  const isPending = createMut.isPending || updateMut.isPending;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className="w-full max-w-[calc(100vw-2rem)] sm:max-w-lg rounded-lg border border-border bg-card p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-foreground">
            {editing ? "Editar passo" : "Novo passo"}
          </h2>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">
              Tipo de passo *
            </label>
            <select
              value={stepType}
              onChange={(e) => {
                const t = e.target.value as StepType;
                setStepType(t);
                if (!editing) {
                  setConfigStr(STEP_CONFIG_PLACEHOLDERS[t] ?? "{}");
                }
              }}
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {(Object.keys(STEP_TYPE_LABELS) as StepType[]).map((s) => (
                <option key={s} value={s}>
                  {STEP_TYPE_LABELS[s]}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">
              Config (JSON)
            </label>
            <textarea
              rows={5}
              value={configStr}
              onChange={(e) => {
                setConfigStr(e.target.value);
                setConfigError("");
              }}
              placeholder={STEP_CONFIG_PLACEHOLDERS[stepType] ?? "{}"}
              className="flex w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-y"
            />
            {configError && (
              <p className="mt-1 text-xs text-destructive">{configError}</p>
            )}
          </div>
          <div className="flex justify-end gap-3 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-muted transition-colors"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={isPending}
              className="inline-flex items-center gap-2 rounded-md bg-primary px-5 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Salvando...
                </>
              ) : editing ? (
                "Salvar passo"
              ) : (
                "Adicionar passo"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Steps editor (expandable panel per flow)
// ---------------------------------------------------------------------------

function StepsEditor({ flow }: { flow: Flow }) {
  const { data: steps, isLoading, error, refetch } = useSteps(flow.id);
  const deleteMut = useDeleteStep();
  const [stepDialogOpen, setStepDialogOpen] = useState(false);
  const [editingStep, setEditingStep] = useState<Step | null>(null);
  const [confirmDeleteStep, setConfirmDeleteStep] = useState<Step | null>(null);

  if (isLoading) return <LoadingState label="Carregando passos..." />;
  if (error)
    return <ErrorState message={error.message} onRetry={() => refetch()} />;

  const sortedSteps = [...(steps ?? [])].sort((a, b) => a.ord - b.ord);
  const nextOrd = sortedSteps.length > 0
    ? sortedSteps[sortedSteps.length - 1].ord + 1
    : 0;

  return (
    <div className="mt-3 space-y-3 pl-4 border-l-2 border-primary/20">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          {sortedSteps.length} {sortedSteps.length === 1 ? "passo" : "passos"}
        </span>
        <button
          onClick={() => {
            setEditingStep(null);
            setStepDialogOpen(true);
          }}
          className="inline-flex items-center gap-1.5 rounded-md bg-primary/10 px-3 py-1 text-xs font-medium text-primary hover:bg-primary/20 transition-colors"
        >
          <Plus className="h-3 w-3" />
          Novo passo
        </button>
      </div>

      {sortedSteps.length === 0 ? (
        <p className="text-xs text-muted-foreground py-2">
          Nenhum passo adicionado. Adicione o primeiro passo acima.
        </p>
      ) : (
        <div className="space-y-1.5">
          {sortedSteps.map((step, idx) => (
            <div
              key={step.id}
              className="flex items-start gap-3 rounded-md border border-border bg-muted/30 px-3 py-2"
            >
              <div className="flex-shrink-0 flex items-center gap-2 mt-0.5">
                <span className="text-xs font-mono text-muted-foreground w-4 text-right">
                  {idx + 1}.
                </span>
                <ArrowRight className="h-3 w-3 text-muted-foreground" />
              </div>
              <div className="flex-1 min-w-0">
                <span
                  className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${STEP_TYPE_COLORS[step.step_type]}`}
                >
                  {STEP_TYPE_LABELS[step.step_type]}
                </span>
                {Object.keys(step.config).length > 0 && (
                  <p className="mt-1 text-xs text-muted-foreground font-mono truncate">
                    {JSON.stringify(step.config)}
                  </p>
                )}
              </div>
              <div className="flex-shrink-0 flex items-center gap-1">
                <button
                  onClick={() => {
                    setEditingStep(step);
                    setStepDialogOpen(true);
                  }}
                  className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                  title="Editar passo"
                >
                  <Pencil className="h-3.5 w-3.5" />
                </button>
                <button
                  onClick={() => setConfirmDeleteStep(step)}
                  className="rounded-md p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                  title="Remover passo"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <StepDialog
        open={stepDialogOpen}
        flowId={flow.id}
        editing={editingStep}
        nextOrd={nextOrd}
        onClose={() => setStepDialogOpen(false)}
      />

      {confirmDeleteStep && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => setConfirmDeleteStep(null)}
        >
          <div
            className="w-full max-w-[calc(100vw-2rem)] sm:max-w-md rounded-lg border border-border bg-card p-6 shadow-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="mb-2 text-lg font-semibold text-foreground">
              Remover passo
            </h2>
            <p className="mb-6 text-sm text-muted-foreground">
              Remover o passo{" "}
              <strong className="text-foreground">
                {STEP_TYPE_LABELS[confirmDeleteStep.step_type]}
              </strong>{" "}
              (ordem {confirmDeleteStep.ord})?
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setConfirmDeleteStep(null)}
                className="rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-muted transition-colors"
              >
                Cancelar
              </button>
              <button
                onClick={() => {
                  deleteMut.mutate(
                    { stepId: confirmDeleteStep.id, flowId: flow.id },
                    { onSettled: () => setConfirmDeleteStep(null) },
                  );
                }}
                disabled={deleteMut.isPending}
                className="inline-flex items-center gap-2 rounded-md bg-destructive px-5 py-2 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 transition-colors disabled:opacity-50"
              >
                {deleteMut.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : null}
                Remover
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Trigger dialog
// ---------------------------------------------------------------------------

function TriggerDialog({
  open,
  flow,
  onClose,
}: {
  open: boolean;
  flow: Flow;
  onClose: () => void;
}) {
  const triggerMut = useTriggerFlow();
  const [leadId, setLeadId] = useState("");

  if (!open) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    await triggerMut.mutateAsync({ flowId: flow.id, lead_id: leadId });
    onClose();
    setLeadId("");
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className="w-full max-w-[calc(100vw-2rem)] sm:max-w-md rounded-lg border border-border bg-card p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-foreground">
            Disparar fluxo
          </h2>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <p className="mb-4 text-sm text-muted-foreground">
          Disparar{" "}
          <strong className="text-foreground">{flow.name}</strong> para um lead.
        </p>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">
              ID do lead (UUID) *
            </label>
            <input
              type="text"
              required
              value={leadId}
              onChange={(e) => setLeadId(e.target.value)}
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 font-mono text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>
          <div className="flex justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-muted transition-colors"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={triggerMut.isPending}
              className="inline-flex items-center gap-2 rounded-md bg-primary px-5 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {triggerMut.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Disparando...
                </>
              ) : (
                <>
                  <Play className="h-4 w-4" />
                  Disparar
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Flows tab
// ---------------------------------------------------------------------------

function FlowsTab() {
  const { data: flows, isLoading, error, refetch } = useFlows();
  const deleteMut = useDeleteFlow();
  const updateMut = useUpdateFlow();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Flow | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<Flow | null>(null);
  const [expandedFlow, setExpandedFlow] = useState<string | null>(null);
  const [triggerFlow, setTriggerFlow] = useState<Flow | null>(null);

  if (isLoading) return <LoadingState label="Carregando fluxos..." />;
  if (error)
    return <ErrorState message={error.message} onRetry={() => refetch()} />;

  const items = flows ?? [];

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <button
          onClick={() => {
            setEditing(null);
            setDialogOpen(true);
          }}
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          <Plus className="h-4 w-4" />
          Novo fluxo
        </button>
      </div>

      {items.length === 0 ? (
        <EmptyState
          label="Nenhum fluxo de automacao encontrado"
          onAdd={() => {
            setEditing(null);
            setDialogOpen(true);
          }}
        />
      ) : (
        <div className="space-y-2">
          {items.map((flow) => {
            const isExpanded = expandedFlow === flow.id;
            return (
              <div
                key={flow.id}
                className="rounded-lg border border-border bg-card"
              >
                {/* Flow row */}
                <div className="flex items-center gap-3 px-4 py-3">
                  {/* Expand toggle */}
                  <button
                    onClick={() =>
                      setExpandedFlow(isExpanded ? null : flow.id)
                    }
                    className="flex-shrink-0 rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                    title={isExpanded ? "Recolher passos" : "Expandir passos"}
                  >
                    {isExpanded ? (
                      <ChevronUp className="h-4 w-4" />
                    ) : (
                      <ChevronDown className="h-4 w-4" />
                    )}
                  </button>

                  {/* Flow info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-foreground truncate">
                        {flow.name}
                      </span>
                      <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                        {TRIGGER_LABELS[flow.trigger_type] ?? flow.trigger_type}
                      </span>
                    </div>
                  </div>

                  {/* Active toggle */}
                  <div className="flex-shrink-0 flex items-center gap-1.5">
                    <button
                      onClick={() =>
                        updateMut.mutate({
                          id: flow.id,
                          active: !flow.active,
                        })
                      }
                      disabled={updateMut.isPending}
                      title={
                        flow.active ? "Desativar fluxo" : "Ativar fluxo"
                      }
                      className={`relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus:outline-none ${
                        flow.active ? "bg-primary" : "bg-muted-foreground/30"
                      } disabled:opacity-50`}
                    >
                      <span
                        className={`inline-block h-4 w-4 transform rounded-full bg-white shadow-lg transition-transform ${
                          flow.active ? "translate-x-4" : "translate-x-0"
                        }`}
                      />
                    </button>
                  </div>

                  {/* Actions */}
                  <div className="flex-shrink-0 flex items-center gap-1">
                    <button
                      onClick={() => setTriggerFlow(flow)}
                      className="rounded-md p-1.5 text-muted-foreground hover:bg-primary/10 hover:text-primary transition-colors"
                      title="Disparar fluxo"
                    >
                      <Play className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => {
                        setEditing(flow);
                        setDialogOpen(true);
                      }}
                      className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                      title="Editar fluxo"
                    >
                      <Pencil className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => setConfirmDelete(flow)}
                      className="rounded-md p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                      title="Remover fluxo"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>

                {/* Steps editor (expandable) */}
                {isExpanded && (
                  <div className="px-4 pb-4">
                    <StepsEditor flow={flow} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      <FlowDialog
        open={dialogOpen}
        editing={editing}
        onClose={() => setDialogOpen(false)}
      />

      {triggerFlow && (
        <TriggerDialog
          open={!!triggerFlow}
          flow={triggerFlow}
          onClose={() => setTriggerFlow(null)}
        />
      )}

      {confirmDelete && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => setConfirmDelete(null)}
        >
          <div
            className="w-full max-w-[calc(100vw-2rem)] sm:max-w-md rounded-lg border border-border bg-card p-6 shadow-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="mb-2 text-lg font-semibold text-foreground">
              Remover fluxo
            </h2>
            <p className="mb-6 text-sm text-muted-foreground">
              Tem certeza que deseja remover o fluxo{" "}
              <strong className="text-foreground">{confirmDelete.name}</strong>?
              Todos os passos e execucoes serao perdidos.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setConfirmDelete(null)}
                className="rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-muted transition-colors"
              >
                Cancelar
              </button>
              <button
                onClick={() => {
                  deleteMut.mutate(confirmDelete.id, {
                    onSettled: () => setConfirmDelete(null),
                  });
                }}
                disabled={deleteMut.isPending}
                className="inline-flex items-center gap-2 rounded-md bg-destructive px-5 py-2 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 transition-colors disabled:opacity-50"
              >
                {deleteMut.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : null}
                Confirmar remocao
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Executions tab
// ---------------------------------------------------------------------------

function ExecutionsTab() {
  const { data: executions, isLoading, error, refetch } = useExecutions();
  const cancelMut = useCancelExecution();
  const runDueMut = useRunDue();
  const [confirmCancel, setConfirmCancel] = useState<Execution | null>(null);

  if (isLoading) return <LoadingState label="Carregando execucoes..." />;
  if (error)
    return <ErrorState message={error.message} onRetry={() => refetch()} />;

  const items = executions ?? [];

  return (
    <div className="space-y-4">
      {/* Run-due button */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {items.length} {items.length === 1 ? "execucao" : "execucoes"} listadas
        </p>
        <button
          onClick={() => runDueMut.mutate()}
          disabled={runDueMut.isPending}
          className="inline-flex items-center gap-2 rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-muted transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {runDueMut.isPending ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Processando...
            </>
          ) : (
            <>
              <RefreshCw className="h-4 w-4" />
              Executar acoes pendentes
            </>
          )}
        </button>
      </div>

      {items.length === 0 ? (
        <EmptyState label="Nenhuma execucao encontrada" />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border bg-muted/50">
              <tr>
                <th className="px-4 py-3 font-medium text-muted-foreground">
                  Status
                </th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden sm:table-cell">
                  Lead ID
                </th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">
                  Passo atual
                </th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden lg:table-cell">
                  Proxima acao
                </th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden xl:table-cell">
                  Erro
                </th>
                <th className="px-4 py-3 font-medium text-muted-foreground">
                  Acoes
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {items.map((exec) => {
                const StatusIcon =
                  EXECUTION_STATUS_ICONS[exec.status] ?? Clock;
                const isRunning = exec.status === "running";
                return (
                  <tr
                    key={exec.id}
                    className="bg-card hover:bg-muted/20 transition-colors"
                  >
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${EXECUTION_STATUS_COLORS[exec.status] ?? ""}`}
                      >
                        <StatusIcon
                          className={`h-3 w-3 ${exec.status === "running" ? "animate-spin" : ""}`}
                        />
                        {EXECUTION_STATUS_LABELS[exec.status] ?? exec.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-foreground hidden sm:table-cell">
                      <span className="font-mono text-xs truncate block max-w-[140px]">
                        {exec.lead_id}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-foreground hidden md:table-cell">
                      Passo {exec.current_step_ord + 1}
                    </td>
                    <td className="px-4 py-3 text-foreground hidden lg:table-cell">
                      {exec.next_action_at
                        ? new Date(exec.next_action_at).toLocaleString("pt-BR")
                        : "—"}
                    </td>
                    <td className="px-4 py-3 text-foreground hidden xl:table-cell">
                      {exec.error_detail ? (
                        <span className="text-destructive text-xs truncate block max-w-[200px]">
                          {exec.error_detail}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {isRunning && (
                        <button
                          onClick={() => setConfirmCancel(exec)}
                          className="rounded-md p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                          title="Cancelar execucao"
                        >
                          <XCircle className="h-4 w-4" />
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {confirmCancel && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => setConfirmCancel(null)}
        >
          <div
            className="w-full max-w-[calc(100vw-2rem)] sm:max-w-md rounded-lg border border-border bg-card p-6 shadow-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="mb-2 text-lg font-semibold text-foreground">
              Cancelar execucao
            </h2>
            <p className="mb-6 text-sm text-muted-foreground">
              Cancelar esta execucao para o lead{" "}
              <strong className="font-mono text-foreground text-xs">
                {confirmCancel.lead_id}
              </strong>
              ?
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setConfirmCancel(null)}
                className="rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-muted transition-colors"
              >
                Voltar
              </button>
              <button
                onClick={() => {
                  cancelMut.mutate(confirmCancel.id, {
                    onSettled: () => setConfirmCancel(null),
                  });
                }}
                disabled={cancelMut.isPending}
                className="inline-flex items-center gap-2 rounded-md bg-destructive px-5 py-2 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 transition-colors disabled:opacity-50"
              >
                {cancelMut.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : null}
                Confirmar cancelamento
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

type TabKey = "flows" | "executions";

const TABS: { key: TabKey; label: string; icon: React.ElementType }[] = [
  { key: "flows", label: "Fluxos", icon: Zap },
  { key: "executions", label: "Execucoes", icon: Play },
];

export default function Automacao() {
  const [activeTab, setActiveTab] = useState<TabKey>("flows");

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Zap className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold text-foreground">Automacao</h1>
          <p className="text-sm text-muted-foreground">
            Fluxos de automacao WhatsApp — gatilhos, passos e execucoes
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-border">
        <nav className="flex gap-0 -mb-px">
          {TABS.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                activeTab === key
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground hover:border-border"
              }`}
            >
              <Icon className="h-4 w-4" />
              <span className="hidden sm:inline">{label}</span>
            </button>
          ))}
        </nav>
      </div>

      {/* Tab content */}
      <div>
        {activeTab === "flows" && <FlowsTab />}
        {activeTab === "executions" && <ExecutionsTab />}
      </div>
    </div>
  );
}

/*
 * STATUS_PAGINA NOTE:
 * This page uses route key "automacao".
 * The tech-lead must insert a row in status_pagina:
 *   page_key = "automacao", product = "orbity", active = true
 * until this row exists, the nav item will be HIDDEN by filterNavByPageStatus.
 */
