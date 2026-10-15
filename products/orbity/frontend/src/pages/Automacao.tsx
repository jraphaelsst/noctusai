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
import { useConfirm } from "@noctusai/lib/components";
import { LeadSelect } from "@/components/LeadSelect";
import { useLeadOptions, nameLookup } from "@/hooks/useClients";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useFunil } from "@/hooks/useCrm";
import {
  TriggerConfigFields,
  buildTriggerConfig,
  subjectLabel,
} from "@/components/TriggerConfigFields";
import { useWhatsAppConnectionState } from "@/hooks/useWhatsApp";
import {
  SendMessageFields,
  WaitFields,
  buildSendMessageConfig,
  buildWaitConfig,
  parseWaitConfig,
  type WaitUnit,
} from "@/components/StepConfigForm";
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
  owner_changed: "Responsável alterado",
  task_created: "Tarefa criada",
  task_completed: "Tarefa concluída",
  meeting_created: "Reunião criada",
  proposal_sent: "Proposta enviada",
  client_created: "Cliente criado",
  lead_status_changed: "Status do lead alterado",
  manual: "Manual",
};

/**
 * Triggers the backend actually EMITS (automation_triggers.py `disparar`).
 * The rest stay visible as "em breve" but are not selectable, so a gestor never
 * builds a flow that silently never runs. Add a type here in the same commit
 * that adds its emitter.
 */
const LIVE_TRIGGERS: ReadonlySet<TriggerType> = new Set<TriggerType>([
  "manual",
  "lead_created",
  "pipeline_stage_entered",
  "lead_status_changed",
  "task_created",
  "task_completed",
  "client_created",
  "meeting_created",
  "whatsapp_message_received",
  "keyword_received",
]);

const STEP_TYPE_LABELS: Record<StepType, string> = {
  send_message: "Enviar mensagem",
  send_whatsapp_media: "Enviar midia WhatsApp",
  wait: "Aguardar",
  condition: "Condição",
  action: "Ação",
  branch: "Ramificação",
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
  processing: "Processando",
  done: "Concluida",
  canceled: "Cancelada",
  failed: "Falhou",
};

const EXECUTION_STATUS_COLORS: Record<string, string> = {
  running:
    "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
  processing:
    "bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-400",
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

/**
 * Remount per open/target so form state never leaks from a previous
 * create/edit (re-opening "Novo" used to come back pre-filled).
 */
function FlowDialog(props: React.ComponentProps<typeof FlowDialogInner>) {
  if (!props.open) return null;
  return <FlowDialogInner key={props.editing?.id ?? "new"} {...props} />;
}

function FlowDialogInner({
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
  const initCfg = editing?.trigger_config ?? {};
  const [keyword, setKeyword] = useState(String(initCfg.keyword ?? ""));
  const [stageId, setStageId] = useState(String(initCfg.stage_id ?? ""));
  const [leadStatus, setLeadStatus] = useState(String(initCfg.status ?? ""));
  const [stopOnReply, setStopOnReply] = useState(
    (editing?.stop_rules ?? {}).stop_on_reply !== false,
  );
  const [cfgError, setCfgError] = useState("");
  const funilQ = useFunil();
  const stages = (funilQ.data ?? []).map((f) => f.stage);

  if (!open) return null;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const built = buildTriggerConfig(form.trigger_type, editing?.trigger_config, {
      keyword,
      stageId,
      leadStatus,
    });
    if (built.error || !built.config) {
      setCfgError(built.error ?? "Configuração inválida");
      return;
    }
    setCfgError("");
    const payload: FlowCreate = {
      ...form,
      trigger_config: built.config,
      stop_rules: { ...(editing?.stop_rules ?? {}), stop_on_reply: stopOnReply },
    };
    // mutate + onSuccess: hook toasts errors; dialog stays open on failure.
    if (editing) {
      updateMut.mutate({ id: editing.id, ...payload }, { onSuccess: onClose });
    } else {
      createMut.mutate(payload, { onSuccess: onClose });
    }
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
            {editing ? "Editar fluxo" : "Novo fluxo de automação"}
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
            <label htmlFor="aut-nome" className="mb-1 block text-sm font-medium text-foreground">Nome *</label>
            <input id="aut-nome"
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
            <label htmlFor="aut-gatilho" className="mb-1 block text-sm font-medium text-foreground">Gatilho *</label>
            <select id="aut-gatilho"
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
                <option key={t} value={t} disabled={!LIVE_TRIGGERS.has(t)}>
                  {LIVE_TRIGGERS.has(t) ? TRIGGER_LABELS[t] : `${TRIGGER_LABELS[t]} (em breve)`}
                </option>
              ))}
            </select>
          </div>
          <TriggerConfigFields
            triggerType={form.trigger_type}
            keyword={keyword}
            onKeyword={(v) => { setKeyword(v); setCfgError(""); }}
            stageId={stageId}
            onStageId={setStageId}
            stages={stages}
            leadStatus={leadStatus}
            onLeadStatus={setLeadStatus}
            error={cfgError}
          />
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="aut-stop-on-reply"
              checked={stopOnReply}
              onChange={(e) => setStopOnReply(e.target.checked)}
              className="h-4 w-4 rounded border-input accent-primary"
            />
            <label htmlFor="aut-stop-on-reply" className="text-sm font-medium text-foreground">
              Parar quando o lead responder
            </label>
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
                "Salvar alterações"
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
  send_message: '{"template": "Olá {{nome}}, bem-vindo!"}',
  send_whatsapp_media:
    '{"template": "Confira nosso material", "media_url": "https://..."}',
  wait: '{"duration_minutes": 60}',
  condition: '{"field": "status", "operator": "eq", "value": "new"}',
  action: '{"action_type": "add_tag", "tag": "interessado"}',
  branch: '{"branches": []}',
  end: "{}",
};

/**
 * Remount per open/target so form state never leaks from a previous
 * create/edit (re-opening "Novo" used to come back pre-filled).
 */
function StepDialog(props: React.ComponentProps<typeof StepDialogInner>) {
  if (!props.open) return null;
  return <StepDialogInner key={props.editing?.id ?? "new"} {...props} />;
}

function StepDialogInner({
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
  const [advanced, setAdvanced] = useState(false);
  const [template, setTemplate] = useState<string>(
    editing?.step_type === "send_message" ? String(editing.config.template ?? "") : "",
  );
  const initialWait = parseWaitConfig(editing?.step_type === "wait" ? editing.config : undefined);
  const [waitAmount, setWaitAmount] = useState(initialWait.amount);
  const [waitUnit, setWaitUnit] = useState<WaitUnit>(initialWait.unit);
  const hasForm = stepType === "send_message" || stepType === "wait";
  const showForm = hasForm && !advanced;

  if (!open) return null;

  function parseConfig(): Record<string, unknown> | null {
    const raw = configStr.trim() || "{}";
    try {
      return JSON.parse(raw);
    } catch {
      setConfigError("JSON inválido");
      return null;
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setConfigError("");
    let config: Record<string, unknown> | null;
    if (showForm) {
      const base = editing && editing.step_type === stepType ? editing.config : {};
      const built =
        stepType === "send_message"
          ? buildSendMessageConfig(template, base)
          : buildWaitConfig(waitAmount, waitUnit, base);
      if (built.error || !built.config) {
        setConfigError(built.error ?? "Configuração inválida");
        return;
      }
      config = built.config;
    } else {
      config = parseConfig();
    }
    if (config === null) return;

    if (editing) {
      updateMut.mutate(
        { stepId: editing.id, flowId, step_type: stepType, config },
        { onSuccess: onClose },
      );
    } else {
      const payload: StepCreate = {
        ord: nextOrd,
        step_type: stepType,
        config,
      };
      createMut.mutate(payload, { onSuccess: onClose });
    }
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
            <label htmlFor="aut-tipo-de-passo" className="mb-1 block text-sm font-medium text-foreground">Tipo de passo *</label>
            <select id="aut-tipo-de-passo"
              value={stepType}
              onChange={(e) => {
                const t = e.target.value as StepType;
                setStepType(t);
                setConfigError("");
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
          {stepType === "send_message" && showForm && (
            <SendMessageFields template={template} onChange={(v) => { setTemplate(v); setConfigError(""); }} />
          )}
          {stepType === "wait" && showForm && (
            <WaitFields
              amount={waitAmount}
              unit={waitUnit}
              onChange={(a, u) => { setWaitAmount(a); setWaitUnit(u); setConfigError(""); }}
            />
          )}
          {!showForm && (
          <div>
            <label htmlFor="aut-config-json" className="mb-1 block text-sm font-medium text-foreground">Config (JSON)</label>
            <textarea id="aut-config-json"
              rows={5}
              value={configStr}
              onChange={(e) => {
                setConfigStr(e.target.value);
                setConfigError("");
              }}
              placeholder={STEP_CONFIG_PLACEHOLDERS[stepType] ?? "{}"}
              className="flex w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-y"
            />
          </div>
          )}
          {configError && (
            <p role="alert" className="text-xs text-destructive">{configError}</p>
          )}
          {hasForm && (
            <button
              type="button"
              onClick={() => {
                if (!advanced) {
                  const built =
                    stepType === "send_message"
                      ? buildSendMessageConfig(template || " ", editing?.config)
                      : buildWaitConfig(waitAmount, waitUnit, editing?.config);
                  if (built.config) {
                    const c = { ...built.config };
                    if (stepType === "send_message") c.template = template;
                    setConfigStr(JSON.stringify(c, null, 2));
                  }
                }
                setAdvanced(!advanced);
                setConfigError("");
              }}
              className="text-xs text-muted-foreground underline hover:text-foreground"
            >
              {advanced ? "Voltar ao formulário" : "Avançado (JSON)"}
            </button>
          )}
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
  const { data: steps, isPending, error, refetch } = useSteps(flow.id);
  const deleteMut = useDeleteStep();
  const [stepDialogOpen, setStepDialogOpen] = useState(false);
  const [editingStep, setEditingStep] = useState<Step | null>(null);
  const confirm = useConfirm();
  const askDeleteStep = async (step: Step) => {
    if (
      await confirm({
        title: `Remover o passo ${STEP_TYPE_LABELS[step.step_type]} (ordem ${step.ord})?`,
        confirmLabel: "Remover",
        tone: "danger",
      })
    ) {
      deleteMut.mutate({ stepId: step.id, flowId: flow.id });
    }
  };

  if (isPending && !steps) return <LoadingState label="Carregando passos..." />;
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
                  onClick={() => void askDeleteStep(step)}
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

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!leadId) return;
    triggerMut.mutate(
      { flowId: flow.id, lead_id: leadId },
      { onSuccess: () => { setLeadId(""); onClose(); } },
    );
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
          <LeadSelect value={leadId} onChange={(id) => setLeadId(id ?? "")} id="trigger-lead" required />
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
  const { data: flows, isPending, error, refetch } = useFlows();
  const deleteMut = useDeleteFlow();
  const updateMut = useUpdateFlow();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Flow | null>(null);
  const confirm = useConfirm();
  const askDeleteFlow = async (item: Flow) => {
    if (
      await confirm({
        title: `Remover fluxo "${item.name}"?`,
        description: "Esta ação não pode ser desfeita.",
        confirmLabel: "Remover",
        tone: "danger",
      })
    ) {
      deleteMut.mutate(item.id);
    }
  };
  const [expandedFlow, setExpandedFlow] = useState<string | null>(null);
  const [triggerFlow, setTriggerFlow] = useState<Flow | null>(null);

  if (isPending && !flows) return <LoadingState label="Carregando fluxos..." />;
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
          label="Nenhum fluxo de automação encontrado"
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
                      onClick={() => void askDeleteFlow(flow)}
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

    </div>
  );
}

// ---------------------------------------------------------------------------
// Executions tab
// ---------------------------------------------------------------------------

function WhatsAppStatusBanner() {
  const state = useWhatsAppConnectionState();
  if (state.kind === "loading") return null;
  if (state.kind === "connected") {
    return (
      <div
        role="note"
        data-testid="wa-banner-connected"
        className="flex items-start gap-2 rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-xs text-emerald-900"
      >
        <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5" />
        <span>
          WhatsApp conectado
          {state.number ? <> · <strong>{state.number}</strong></> : null} ({state.label}, sessão {state.session}).
        </span>
      </div>
    );
  }
  const message =
    state.kind === "error"
      ? `Não foi possível verificar a conexão do WhatsApp (${state.message}) — mensagens podem não ser enviadas.`
      : "WhatsApp não conectado — mensagens não serão enviadas.";
  return (
    <div
      role="note"
      data-testid="wa-banner-disconnected"
      className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900"
    >
      <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
      <span>
        {message}{" "}
        <Link to="/whatsapp" className="font-medium underline">
          Conectar WhatsApp
        </Link>
      </span>
    </div>
  );
}

function ExecutionsTab() {
  const { data: executions, isPending, error, refetch } = useExecutions();
  const cancelMut = useCancelExecution();
  const runDueMut = useRunDue();
  const confirm = useConfirm();
  const leadsQ = useLeadOptions();
  const leadName = nameLookup(leadsQ.data);
  const askCancel = async (exec: Execution) => {
    if (
      await confirm({
        title: `Cancelar esta execução para o lead ${leadName(exec.lead_id) ?? "selecionado"}?`,
        confirmLabel: "Cancelar execução",
        cancelLabel: "Voltar",
        tone: "danger",
      })
    ) {
      cancelMut.mutate(exec.id);
    }
  };

  if (isPending && !executions) return <LoadingState label="Carregando execuções..." />;
  if (error)
    return <ErrorState message={error.message} onRetry={() => refetch()} />;

  const items = executions ?? [];

  return (
    <div className="space-y-4">
      {/* Run-due button */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {items.length} {items.length === 1 ? "execução" : "execuções"} listadas
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
              Executar ações pendentes
            </>
          )}
        </button>
      </div>

      {items.length === 0 ? (
        <EmptyState label="Nenhuma execução encontrada" />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border bg-muted/50">
              <tr>
                <th className="px-4 py-3 font-medium text-muted-foreground">
                  Status
                </th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden sm:table-cell">
                  Lead
                </th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">
                  Passo atual
                </th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden lg:table-cell">
                  Próxima ação
                </th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden xl:table-cell">
                  Erro
                </th>
                <th className="px-4 py-3 font-medium text-muted-foreground">
                  Ações
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
                      {exec.error_detail && (
                        <span
                          data-testid="exec-failure-reason"
                          className="mt-1 block max-w-[260px] text-xs text-destructive xl:hidden"
                        >
                          {exec.error_detail}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-foreground hidden sm:table-cell">
                      <span className="text-xs truncate block max-w-[180px]">
                        {subjectLabel(exec, leadName)}
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
                        <span className="text-destructive text-xs block max-w-[320px] whitespace-normal break-words" title={exec.error_detail}>
                          {exec.error_detail}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {isRunning && (
                        <button
                          onClick={() => void askCancel(exec)}
                          className="rounded-md p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                          title="Cancelar execução"
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

    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

type TabKey = "flows" | "executions";

const TABS: { key: TabKey; label: string; icon: React.ElementType }[] = [
  { key: "flows", label: "Fluxos", icon: Zap },
  { key: "executions", label: "Execuções", icon: Play },
];

export default function Automacao() {
  const [activeTab, setActiveTab] = useState<TabKey>("flows");

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Zap className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold text-foreground">Automação</h1>
          <p className="text-sm text-muted-foreground">
            Fluxos de automação WhatsApp — gatilhos, passos e execuções
          </p>
        </div>
      </div>

      <WhatsAppStatusBanner />

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
