/**
 * Planejamento tab — monthly content plans (manual or AI-assisted) with
 * progress cards. Loading uses showSkeleton = isPending && !data (never
 * isLoading); a background refetch only shows the small refreshing hint.
 */
import { useState } from "react";
import { AlertCircle, ClipboardList, Loader2, Plus, Trash2 } from "lucide-react";
import { useConfirm } from "@noctusai/lib/components";
import { useCampaigns } from "@/hooks/useConteudo";
import { planProgress, useContentPlans, useDeletePlan, type ContentPlan } from "@/hooks/useContentPlans";
import { ManualPlanDialog } from "./PlanDialogs";
import { PlanSheet } from "./PlanSheet";
import { BTN_PRIMARY, PLATFORM_LABEL } from "./PlanUi";

function PlanCard({ plan, onOpen, onDelete }: { plan: ContentPlan; onOpen: () => void; onDelete: () => void }) {
  const { total, done, percent } = planProgress(plan);
  const discarded = plan.items.filter((i) => i.status === "discarded").length;
  const platforms = [...new Set(plan.items.map((i) => i.platform).filter(Boolean))] as string[];
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4">
      <div className="flex items-start justify-between gap-2">
        <button type="button" onClick={onOpen} className="min-w-0 text-left">
          <p className="truncate font-semibold text-foreground hover:underline">{plan.title}</p>
          <p className="text-xs text-muted-foreground">{plan.month}</p>
        </button>
        <button type="button" aria-label={`Remover ${plan.title}`} onClick={onDelete}
          className="rounded-md p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive">
          <Trash2 className="h-4 w-4" />
        </button>
      </div>
      <div className="flex flex-wrap gap-1.5 text-[10px]">
        <span className="rounded-full border px-2 py-0.5">{plan.creation_mode === "manual" ? "Manual" : "IA"}</span>
        <span className="rounded-full border px-2 py-0.5">{plan.status === "active" ? "Ativo" : "Rascunho"}</span>
        {discarded > 0 && <span className="rounded-full border px-2 py-0.5">{discarded} descartados</span>}
        {platforms.map((p) => <span key={p} className="rounded-full border px-2 py-0.5">{PLATFORM_LABEL[p]}</span>)}
      </div>
      <div>
        <div className="mb-1 flex justify-between text-xs text-muted-foreground">
          <span>{done}/{total} com tarefa</span>
          <span>{percent}%</span>
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuenow={percent}
          aria-valuemin={0} aria-valuemax={100}>
          <div className="h-full bg-primary" style={{ width: `${percent}%` }} />
        </div>
      </div>
    </div>
  );
}

export function PlanejamentoTab() {
  const confirm = useConfirm();
  const { data, isPending, isFetching, error, refetch } = useContentPlans();
  const { data: campaignsData } = useCampaigns();
  const deletePlan = useDeletePlan();
  const [creating, setCreating] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);

  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;
  const plans = data?.items ?? [];
  const openPlan = plans.find((p) => p.id === openId) ?? null;

  async function askDelete(plan: ContentPlan) {
    const ok = await confirm({
      title: `Remover planejamento "${plan.title}"?`,
      description: "Os conteúdos do plano serão removidos. Tarefas e posts já criados continuam existindo.",
      confirmLabel: "Remover",
      tone: "danger",
    });
    if (ok) deletePlan.mutate(plan.id);
  }

  if (showSkeleton) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-16">
        <Loader2 className="h-7 w-7 animate-spin text-primary" />
        <p className="text-sm text-muted-foreground">Carregando planejamentos...</p>
      </div>
    );
  }
  if (error && !data) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-16 text-destructive">
        <AlertCircle className="h-7 w-7" />
        <p className="text-sm font-medium">Erro ao carregar planejamentos</p>
        <p className="max-w-sm text-center text-xs text-muted-foreground">{error.message}</p>
        <button onClick={() => void refetch()}
          className="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-1.5 text-xs font-medium text-destructive">
          Tentar novamente
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-end gap-3">
        {isRefreshing && <span className="text-xs text-muted-foreground">Atualizando...</span>}
        <button type="button" onClick={() => setCreating(true)} className={BTN_PRIMARY}>
          <Plus className="h-4 w-4" /> Novo planejamento
        </button>
      </div>

      {plans.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-3 py-16">
          <ClipboardList className="h-8 w-8 text-muted-foreground/40" />
          <p className="text-sm text-muted-foreground">Nenhum planejamento criado</p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {plans.map((plan) => (
            <PlanCard key={plan.id} plan={plan} onOpen={() => setOpenId(plan.id)} onDelete={() => void askDelete(plan)} />
          ))}
        </div>
      )}

      {creating && (
        <ManualPlanDialog
          campaigns={campaignsData?.items ?? []}
          onClose={() => setCreating(false)}
          onCreated={(plan) => {
            setCreating(false);
            setOpenId(plan.id);
          }}
        />
      )}
      {openPlan && <PlanSheet key={openPlan.id} plan={openPlan} onClose={() => setOpenId(null)} />}
    </div>
  );
}
