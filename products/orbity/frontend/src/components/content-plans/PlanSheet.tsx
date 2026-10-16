/**
 * Plan sheet — opens directly in edit mode: editable header, ordered items
 * (reorder / edit / delete), tasks from selected items, item -> post, AI.
 */
import { useState } from "react";
import { ArrowDown, ArrowUp, FilePlus2, ListTodo, Loader2, Pencil, Plus, Sparkles, Trash2, X } from "lucide-react";
import { useConfirm } from "@noctusai/lib/components";
import {
  isTaskEligible,
  planProgress,
  useCreateTasksFromItems,
  useDeletePlanItem,
  usePromoteItemToPost,
  useReorderPlanItems,
  useUpdatePlan,
  type ContentPlan,
  type PlanItem,
} from "@/hooks/useContentPlans";
import { AIGenerateDialog } from "./AIGenerateDialog";
import { ItemDialog } from "./PlanDialogs";
import {
  BTN_OUTLINE,
  BTN_PRIMARY,
  fmtDay,
  INPUT_CLS,
  ITEM_STATUS_COLOR,
  ITEM_STATUS_LABEL,
  PLATFORM_LABEL,
  TEXTAREA_CLS,
} from "./PlanUi";

export function PlanSheet({ plan, onClose }: { plan: ContentPlan; onClose: () => void }) {
  const confirm = useConfirm();
  const updatePlan = useUpdatePlan();
  const deleteItem = useDeletePlanItem();
  const reorder = useReorderPlanItems();
  const createTasks = useCreateTasksFromItems();
  const promote = usePromoteItemToPost();

  const notesValue = typeof plan.strategy_context?.notes === "string" ? (plan.strategy_context.notes as string) : "";
  const [title, setTitle] = useState(plan.title);
  const [status, setStatus] = useState(plan.status);
  const [notes, setNotes] = useState(notesValue);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [itemDialog, setItemDialog] = useState<{ editing: PlanItem | null } | null>(null);
  const [aiOpen, setAiOpen] = useState(false);

  const items = [...plan.items].sort((a, b) => a.order_position - b.order_position);
  const progress = planProgress(plan);
  const dirty = title.trim() !== plan.title || status !== plan.status || notes !== notesValue;
  const eligibleSelected = items.filter((i) => selected.has(i.id) && isTaskEligible(i));

  function saveHeader() {
    updatePlan.mutate({
      id: plan.id,
      title: title.trim(),
      status,
      strategy_context: { ...plan.strategy_context, notes: notes.trim() },
    });
  }

  function move(index: number, delta: -1 | 1) {
    const ids = items.map((i) => i.id);
    const target = index + delta;
    if (target < 0 || target >= ids.length) return;
    [ids[index], ids[target]] = [ids[target], ids[index]];
    reorder.mutate({ planId: plan.id, ids });
  }

  async function askDelete(item: PlanItem) {
    const ok = await confirm({
      title: `Remover "${item.title}"?`,
      description: item.task_id
        ? "O conteúdo será descartado, mas a tarefa já criada continua existindo."
        : "Esta ação não pode ser desfeita.",
      confirmLabel: item.task_id ? "Descartar" : "Remover",
      tone: "danger",
    });
    if (ok) deleteItem.mutate({ planId: plan.id, itemId: item.id });
  }

  function makeTasks() {
    createTasks.mutate(
      { planId: plan.id, itemIds: eligibleSelected.map((i) => i.id) },
      { onSuccess: () => setSelected(new Set()) },
    );
  }

  function toggleSelected(id: string) {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  }

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/40" onClick={onClose}>
      <aside
        aria-label="Detalhes do planejamento"
        className="flex h-full w-full max-w-2xl flex-col gap-4 overflow-y-auto border-l border-border bg-card p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1 space-y-2">
            <input aria-label="Título do planejamento" className={`${INPUT_CLS} text-base font-semibold`}
              value={title} onChange={(e) => setTitle(e.target.value)} />
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span>{plan.month}</span>
              <span className="rounded-full border px-2 py-0.5">{plan.creation_mode === "manual" ? "Manual" : "IA"}</span>
              <select aria-label="Status do planejamento" className="h-7 rounded-md border border-input bg-background px-2 text-xs"
                value={status} onChange={(e) => setStatus(e.target.value as ContentPlan["status"])}>
                <option value="active">Ativo</option>
                <option value="draft">Rascunho</option>
              </select>
              <span>{progress.done}/{progress.total} com tarefa ({progress.percent}%)</span>
            </div>
            <textarea aria-label="Estratégia do planejamento" rows={2} className={TEXTAREA_CLS} value={notes}
              onChange={(e) => setNotes(e.target.value)} placeholder="Estratégia / observações (usado como contexto da IA)" />
            {dirty && (
              <button type="button" onClick={saveHeader} disabled={updatePlan.isPending || !title.trim()} className={BTN_PRIMARY}>
                {updatePlan.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                Salvar alterações
              </button>
            )}
          </div>
          <button onClick={onClose} aria-label="Fechar" className="rounded-md p-1.5 text-muted-foreground hover:bg-muted">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex flex-wrap gap-2">
          <button type="button" className={BTN_OUTLINE} onClick={() => setItemDialog({ editing: null })}>
            <Plus className="h-4 w-4" /> Novo conteúdo
          </button>
          <button type="button" className={BTN_OUTLINE} onClick={() => setAiOpen(true)}>
            <Sparkles className="h-4 w-4" /> Gerar com IA
          </button>
          <button type="button" className={BTN_PRIMARY} disabled={eligibleSelected.length === 0 || createTasks.isPending}
            onClick={makeTasks}>
            {createTasks.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <ListTodo className="h-4 w-4" />}
            Criar tarefas{eligibleSelected.length > 0 ? ` (${eligibleSelected.length})` : ""}
          </button>
        </div>

        {items.length === 0 ? (
          <p className="py-10 text-center text-sm text-muted-foreground">
            Nenhum conteúdo ainda. Adicione manualmente ou gere com IA.
          </p>
        ) : (
          <ul className="space-y-2">
            {items.map((item, index) => (
              <li key={item.id} className={`flex items-start gap-3 rounded-md border border-border p-3 ${
                item.status === "discarded" ? "opacity-60" : ""}`}>
                <input type="checkbox" aria-label={`Selecionar ${item.title}`} className="mt-1"
                  disabled={!isTaskEligible(item)} checked={selected.has(item.id)}
                  onChange={() => toggleSelected(item.id)} />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-foreground">{index + 1}. {item.title}</p>
                  {item.description && <p className="line-clamp-2 text-xs text-muted-foreground">{item.description}</p>}
                  <div className="mt-1.5 flex flex-wrap gap-1.5 text-[10px]">
                    <span className={`rounded-full px-2 py-0.5 font-medium ${ITEM_STATUS_COLOR[item.status]}`}>
                      {ITEM_STATUS_LABEL[item.status]}
                    </span>
                    {item.format && <span className="rounded bg-muted px-1.5 py-0.5">{item.format}</span>}
                    {item.platform && <span className="rounded border px-1.5 py-0.5">{PLATFORM_LABEL[item.platform]}</span>}
                    <span className="rounded border px-1.5 py-0.5">{fmtDay(item.post_date)}</span>
                    {item.post_id && <span className="rounded border border-primary/40 px-1.5 py-0.5 text-primary">Post criado</span>}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-0.5">
                  <button type="button" aria-label="Mover para cima" disabled={index === 0 || reorder.isPending}
                    onClick={() => move(index, -1)} className="rounded-md p-1.5 text-muted-foreground hover:bg-muted disabled:opacity-30">
                    <ArrowUp className="h-4 w-4" />
                  </button>
                  <button type="button" aria-label="Mover para baixo" disabled={index === items.length - 1 || reorder.isPending}
                    onClick={() => move(index, 1)} className="rounded-md p-1.5 text-muted-foreground hover:bg-muted disabled:opacity-30">
                    <ArrowDown className="h-4 w-4" />
                  </button>
                  {item.platform && !item.post_id && item.status !== "discarded" && (
                    <button type="button" aria-label="Criar post a partir do conteúdo" title="Criar post (fluxo de aprovação)"
                      disabled={promote.isPending} onClick={() => promote.mutate({ planId: plan.id, itemId: item.id })}
                      className="rounded-md p-1.5 text-muted-foreground hover:bg-muted">
                      <FilePlus2 className="h-4 w-4" />
                    </button>
                  )}
                  <button type="button" aria-label="Editar conteúdo" onClick={() => setItemDialog({ editing: item })}
                    className="rounded-md p-1.5 text-muted-foreground hover:bg-muted">
                    <Pencil className="h-4 w-4" />
                  </button>
                  <button type="button" aria-label="Remover conteúdo" onClick={() => void askDelete(item)}
                    className="rounded-md p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive">
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </aside>

      {itemDialog && (
        <ItemDialog key={itemDialog.editing?.id ?? "new"} plan={plan} editing={itemDialog.editing}
          onClose={() => setItemDialog(null)} />
      )}
      {aiOpen && <AIGenerateDialog plan={plan} onClose={() => setAiOpen(false)} />}
    </div>
  );
}
