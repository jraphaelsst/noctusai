import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { toast } from "sonner";
import {
  useAutomation,
  useActivateAutomation,
  usePauseAutomation,
  useAddStep,
  useDeleteStep,
  useEnrollments,
  Automation,
  AutomationStep,
} from "@/hooks/useAutomations";
import { Loader2, AlertCircle, ArrowLeft, Play, Pause, Plus, Trash2 } from "lucide-react";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const STATUS_BADGE: Record<Automation["status"], { label: string; cls: string }> = {
  rascunho: { label: "Rascunho", cls: "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300" },
  ativa: { label: "Ativa", cls: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300" },
  pausada: { label: "Pausada", cls: "bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-300" },
};

const TRIGGER_LABEL: Record<string, string> = {
  contact_added: "Contato adicionado",
  tag_added: "Tag adicionada",
  list_joined: "Entrou em lista",
  manual: "Manual",
  webhook: "Webhook",
};

const STEP_TYPES: { value: AutomationStep["tipo"]; label: string }[] = [
  { value: "send_email", label: "Enviar e-mail" },
  { value: "wait", label: "Aguardar" },
  { value: "condition", label: "Condicao" },
  { value: "add_tag", label: "Adicionar tag" },
  { value: "remove_tag", label: "Remover tag" },
  { value: "move_to_list", label: "Mover para lista" },
  { value: "webhook", label: "Webhook" },
];

function fmtDate(iso?: string) {
  if (!iso) return "--";
  return new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function stepSummary(step: AutomationStep) {
  const cfg = step.config;
  switch (step.tipo) {
    case "send_email": return cfg.template_name ?? cfg.template_id ?? "E-mail";
    case "wait": return cfg.days ? `${cfg.days} dia(s)` : cfg.hours ? `${cfg.hours} hora(s)` : JSON.stringify(cfg);
    case "add_tag": return cfg.tag ?? JSON.stringify(cfg);
    case "remove_tag": return cfg.tag ?? JSON.stringify(cfg);
    case "move_to_list": return cfg.list_name ?? cfg.list_id ?? JSON.stringify(cfg);
    default: return JSON.stringify(cfg);
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function AutomationDetail() {
  const { id } = useParams<{ id: string }>();
  const { data, isLoading, isError } = useAutomation(id!);
  const automation: Automation | null = data?.data ?? null;

  const { data: enrollData, isLoading: loadingEnroll } = useEnrollments(id!);
  const enrollments: any[] = enrollData?.data ?? [];

  const activateMut = useActivateAutomation();
  const pauseMut = usePauseAutomation();
  const addStepMut = useAddStep();
  const deleteStepMut = useDeleteStep();

  const [showAddStep, setShowAddStep] = useState(false);
  const [stepTipo, setStepTipo] = useState<AutomationStep["tipo"]>("send_email");
  const [stepConfig, setStepConfig] = useState("{}");

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="text-sm text-muted-foreground">Carregando automacao...</p>
      </div>
    );
  }

  if (isError || !automation) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <AlertCircle className="h-8 w-8 text-destructive" />
        <p className="text-sm text-muted-foreground">Erro ao carregar automacao.</p>
        <Link to="/automations" className="text-sm text-primary hover:underline">Voltar para automacoes</Link>
      </div>
    );
  }

  const badge = STATUS_BADGE[automation.status];
  const steps = automation.steps ?? [];

  function handleActivate() {
    activateMut.mutate(id!, {
      onSuccess: () => toast.success("Automacao ativada!"),
      onError: () => toast.error("Erro ao ativar automacao."),
    });
  }

  function handlePause() {
    pauseMut.mutate(id!, {
      onSuccess: () => toast.success("Automacao pausada."),
      onError: () => toast.error("Erro ao pausar automacao."),
    });
  }

  function handleAddStep() {
    let config: Record<string, any>;
    try {
      config = JSON.parse(stepConfig);
    } catch {
      toast.error("Config JSON invalido.");
      return;
    }
    addStepMut.mutate(
      { automationId: id!, tipo: stepTipo, config },
      {
        onSuccess: () => {
          toast.success("Etapa adicionada!");
          setShowAddStep(false);
          setStepConfig("{}");
        },
        onError: () => toast.error("Erro ao adicionar etapa."),
      }
    );
  }

  function handleDeleteStep(stepId: string) {
    if (!confirm("Excluir esta etapa?")) return;
    deleteStepMut.mutate(
      { automationId: id!, stepId },
      {
        onSuccess: () => toast.success("Etapa removida."),
        onError: () => toast.error("Erro ao remover etapa."),
      }
    );
  }

  const inputCls =
    "flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <Link to="/automations" className="text-muted-foreground hover:text-foreground transition-colors">
            <ArrowLeft className="h-5 w-5" />
          </Link>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-foreground">{automation.nome}</h1>
              <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${badge.cls}`}>
                {badge.label}
              </span>
            </div>
            {automation.descricao && (
              <p className="text-sm text-muted-foreground">{automation.descricao}</p>
            )}
          </div>
        </div>
        <div className="flex gap-2">
          {automation.status === "rascunho" && (
            <button
              onClick={handleActivate}
              disabled={activateMut.isPending}
              className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              <Play className="h-4 w-4" /> Ativar
            </button>
          )}
          {automation.status === "ativa" && (
            <button
              onClick={handlePause}
              disabled={pauseMut.isPending}
              className="inline-flex items-center gap-2 rounded-md bg-orange-500 px-4 py-2 text-sm font-medium text-white hover:bg-orange-600 transition-colors disabled:opacity-50"
            >
              <Pause className="h-4 w-4" /> Pausar
            </button>
          )}
        </div>
      </div>

      {/* Info Card */}
      <div className="rounded-lg border border-border bg-card p-5 space-y-3">
        <h2 className="text-lg font-semibold text-foreground">Informacoes</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-sm">
          <div>
            <p className="text-muted-foreground">Gatilho</p>
            <p className="font-medium text-foreground">{TRIGGER_LABEL[automation.trigger_type] ?? automation.trigger_type}</p>
          </div>
          <div>
            <p className="text-muted-foreground">Status</p>
            <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${badge.cls}`}>
              {badge.label}
            </span>
          </div>
          <div>
            <p className="text-muted-foreground">Criada em</p>
            <p className="font-medium text-foreground">{fmtDate(automation.created_at)}</p>
          </div>
        </div>
      </div>

      {/* Steps */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-foreground">Etapas ({steps.length})</h2>
          <button
            onClick={() => setShowAddStep(!showAddStep)}
            className="inline-flex items-center gap-2 rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium hover:bg-muted transition-colors"
          >
            <Plus className="h-4 w-4" /> Adicionar Etapa
          </button>
        </div>

        {/* Add Step Form */}
        {showAddStep && (
          <div className="rounded-lg border border-border bg-card p-4 space-y-3 max-w-lg">
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Tipo</label>
              <select
                className={inputCls}
                value={stepTipo}
                onChange={(e) => setStepTipo(e.target.value as AutomationStep["tipo"])}
              >
                {STEP_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Config (JSON)</label>
              <textarea
                className="flex min-h-[60px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground font-mono focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-y"
                value={stepConfig}
                onChange={(e) => setStepConfig(e.target.value)}
              />
            </div>
            <button
              onClick={handleAddStep}
              disabled={addStepMut.isPending}
              className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              {addStepMut.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Salvar Etapa
            </button>
          </div>
        )}

        {steps.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border bg-muted/30 p-8 text-center">
            <p className="text-sm text-muted-foreground">Nenhuma etapa configurada nesta automacao.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {steps
              .sort((a, b) => a.posicao - b.posicao)
              .map((step, idx) => (
                <div key={step.id} className="flex items-center gap-3 rounded-lg border border-border bg-card p-4">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-sm font-bold text-primary">
                    {idx + 1}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground">
                      {STEP_TYPES.find((t) => t.value === step.tipo)?.label ?? step.tipo}
                    </p>
                    <p className="text-xs text-muted-foreground truncate">{stepSummary(step)}</p>
                  </div>
                  <button
                    onClick={() => handleDeleteStep(step.id)}
                    disabled={deleteStepMut.isPending}
                    className="text-destructive hover:text-destructive/80 transition-colors disabled:opacity-50"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              ))}
          </div>
        )}
      </div>

      {/* Enrollments */}
      <div className="space-y-4">
        <h2 className="text-lg font-semibold text-foreground">Inscricoes</h2>
        {loadingEnroll ? (
          <div className="flex items-center gap-2 py-4">
            <Loader2 className="h-5 w-5 animate-spin text-primary" />
            <p className="text-sm text-muted-foreground">Carregando inscricoes...</p>
          </div>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-border bg-muted/50">
                <tr>
                  <th className="px-4 py-3 font-medium text-muted-foreground">Contato</th>
                  <th className="px-4 py-3 font-medium text-muted-foreground">E-mail</th>
                  <th className="px-4 py-3 font-medium text-muted-foreground">Status</th>
                  <th className="px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Inscrito em</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {enrollments.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-4 py-8 text-center text-muted-foreground">
                      Nenhuma inscricao registrada nesta automacao.
                    </td>
                  </tr>
                ) : (
                  enrollments.map((en: any) => (
                    <tr key={en.id} className="hover:bg-muted/30 transition-colors">
                      <td className="px-4 py-3 font-medium text-foreground">{en.contact_name ?? en.contact_id}</td>
                      <td className="px-4 py-3 text-muted-foreground">{en.contact_email ?? "--"}</td>
                      <td className="px-4 py-3">
                        <span className="inline-flex rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary">
                          {en.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 hidden md:table-cell text-muted-foreground">
                        {fmtDate(en.enrolled_at ?? en.created_at)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
