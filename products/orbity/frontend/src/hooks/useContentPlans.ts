/**
 * Content plans hooks for Orbity — monthly plans with ordered items.
 *
 * Backend contract: products/orbity/backend/app/schemas/content_plans.py
 * (router: /api/content/plans/*). A plan can be linked to a campaign; an item
 * can become a task (item.task_id) and/or a draft post (item.post_id) that
 * then follows the existing approval flow in useConteudo.
 *
 * Hooks are the ONLY place useQuery/useMutation appears (never in pages).
 */
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listOps, pageOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuthStore } from "@noctusai/seed/infra";
import type { Platform, Post } from "@/hooks/useConteudo";

export type PlanStatus = "draft" | "active";
export type CreationMode = "ai" | "manual";
export type ItemStatus = "planned" | "task_pending" | "task_created" | "in_progress" | "published" | "discarded";

export interface PlanItem {
  id: string;
  org_id: string;
  plan_id: string;
  order_position: number;
  title: string;
  description: string | null;
  format: string | null;
  platform: Platform | null;
  post_date: string | null; // YYYY-MM-DD
  due_date: string | null;
  caption: string | null;
  reference_notes: string | null;
  status: ItemStatus;
  task_id: string | null;
  post_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ContentPlan {
  id: string;
  org_id: string;
  client_id: string | null;
  campaign_id: string | null;
  title: string;
  month: string; // YYYY-MM
  strategy_context: Record<string, unknown>;
  status: PlanStatus;
  creation_mode: CreationMode;
  created_at: string;
  updated_at: string;
  items: PlanItem[];
}

export interface PlanItemInput {
  title: string;
  description?: string;
  format?: string;
  platform?: Platform;
  post_date?: string;
  due_date?: string;
  caption?: string;
  reference_notes?: string;
}

export interface PlanCreate {
  title: string;
  month: string;
  client_id?: string;
  campaign_id?: string;
  strategy_context?: Record<string, unknown>;
  status?: PlanStatus;
  creation_mode?: CreationMode;
  items?: PlanItemInput[];
}

export interface PlanUpdate {
  id: string;
  title?: string;
  month?: string;
  client_id?: string;
  campaign_id?: string;
  strategy_context?: Record<string, unknown>;
  status?: PlanStatus;
}

export interface PlanFilters {
  client_id?: string;
  month?: string;
  status?: PlanStatus;
}

interface ListResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface AIGenerateParams {
  items_count: number;
  period_days: 7 | 14 | 30 | 60 | 90;
  start_date: string;
  weekdays: number[]; // 0 = Domingo ... 6 = Sábado
  platforms: Platform[];
  formats: string[];
  focus?: string;
  objective?: string;
  tone?: string;
  tone_custom?: string;
  audience?: string;
  pillars: string[];
  mix_distribution?: string;
  allow_sales_cta: boolean;
  avoid?: string;
  references?: string;
}

export interface AIGeneratedItem {
  title: string;
  description: string | null;
  format: string | null;
  platform: Platform;
  post_date: string;
  reference_notes: string | null;
}

/** Progress excludes discarded items; counted = has a task or is in progress/published. */
export function planProgress(plan: Pick<ContentPlan, "items">): {
  total: number;
  done: number;
  percent: number;
} {
  const live = plan.items.filter((i) => i.status !== "discarded");
  const done = live.filter(
    (i) => !!i.task_id || i.status === "published" || i.status === "task_created" || i.status === "in_progress",
  ).length;
  return { total: live.length, done, percent: live.length === 0 ? 0 : Math.round((done / live.length) * 100) };
}

/** Items that can still receive a task: no task_id and not discarded. */
export function isTaskEligible(item: Pick<PlanItem, "task_id" | "status">): boolean {
  return !item.task_id && item.status !== "discarded";
}

const KEY = "content-plans";

export function useContentPlans(filters?: PlanFilters) {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: [KEY, filters],
    queryFn: () =>
      api.get<ListResponse<ContentPlan>>("/api/content/plans", {
        client_id: filters?.client_id,
        month: filters?.month,
        status: filters?.status,
        page: 1,
        page_size: 200,
      }),
    placeholderData: (prev) => prev,
    enabled: !!user,
    staleTime: 60 * 1000,
  });
}

type PlansPage = ListResponse<ContentPlan>;
const PLANS = { queryKey: [KEY], match: "prefix" as const };

export function useCreatePlan() {
  return useCacheWriteMutation<ContentPlan, PlanCreate>({
    mutationFn: (data) => api.post<ContentPlan>("/api/content/plans", data),
    // Plans are listed newest first (created_at desc); only the unfiltered list is
    // known to contain the new plan — filtered lists converge on the settle.
    targets: [
      {
        queryKey: [KEY, undefined],
        commit: (old: PlansPage | undefined, saved) => pageOps.prependNewest(old, saved),
      },
    ],
    invalidate: [[KEY]],
    onSuccess: () => {
      toast.success("Planejamento criado!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao criar planejamento", { description: error.message });
    },
  });
}

export function useUpdatePlan() {
  return useCacheWriteMutation<ContentPlan, PlanUpdate>({
    mutationFn: ({ id, ...data }) => api.patch<ContentPlan>(`/api/content/plans/${id}`, data),
    targets: ({ id }) => [
      { ...PLANS, commit: (old: PlansPage | undefined, saved) => pageOps.replace(old, id, saved) },
    ],
    onSuccess: () => {
      toast.success("Planejamento atualizado!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao atualizar planejamento", { description: error.message });
    },
  });
}

export function useDeletePlan() {
  return useCacheWriteMutation<{ deleted: boolean }, string>({
    mutationFn: (id) => api.delete<{ deleted: boolean }>(`/api/content/plans/${id}`),
    targets: [
      { ...PLANS, optimistic: (old: PlansPage | undefined, id) => pageOps.remove(old, id) },
    ],
    onSuccess: () => {
      toast.success("Planejamento removido!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao remover planejamento", { description: error.message });
    },
  });
}

// The item mutations answer with the item(s) only; each commits them into the plan
// that nests them, in every cached plans list.

export function useAppendPlanItems() {
  return useCacheWriteMutation<PlanItem[], { planId: string; items: PlanItemInput[] }>({
    mutationFn: ({ planId, items }) =>
      api.post<PlanItem[]>(`/api/content/plans/${planId}/items`, { items }),
    targets: ({ planId }) => [
      {
        ...PLANS,
        commit: (old: PlansPage | undefined, added) =>
          listOps.within(old, "items", (plans) =>
            listOps.update(plans, planId, (p: ContentPlan) => ({ ...p, items: [...p.items, ...added] })),
          ),
      },
    ],
    onError: (error: Error) => {
      toast.error("Erro ao adicionar conteúdos", { description: error.message });
    },
  });
}

export function useUpdatePlanItem() {
  return useCacheWriteMutation<
    PlanItem,
    { planId: string; itemId: string } & Partial<PlanItemInput> & { status?: ItemStatus }
  >({
    mutationFn: ({ planId, itemId, ...data }) =>
      api.patch<PlanItem>(`/api/content/plans/${planId}/items/${itemId}`, data),
    targets: ({ planId, itemId }) => [
      {
        ...PLANS,
        commit: (old: PlansPage | undefined, saved) =>
          listOps.within(old, "items", (plans) =>
            listOps.update(plans, planId, (p: ContentPlan) => ({
              ...p,
              items: listOps.replace(p.items, itemId, saved) ?? p.items,
            })),
          ),
      },
    ],
    onError: (error: Error) => {
      toast.error("Erro ao atualizar conteúdo", { description: error.message });
    },
  });
}

export function useDeletePlanItem() {
  return useCacheWriteMutation<
    { deleted: boolean; discarded: boolean },
    { planId: string; itemId: string }
  >({
    mutationFn: ({ planId, itemId }) =>
      api.delete<{ deleted: boolean; discarded: boolean }>(`/api/content/plans/${planId}/items/${itemId}`),
    // The server either deletes the item or keeps it as "discarded" (it already has a
    // task/post) — only its answer says which, so this commits instead of drawing.
    targets: ({ planId, itemId }) => [
      {
        ...PLANS,
        commit: (old: PlansPage | undefined, res) =>
          listOps.within(old, "items", (plans) =>
            listOps.update(plans, planId, (p: ContentPlan) => ({
              ...p,
              items: res.discarded
                ? (listOps.patch(p.items, itemId, { status: "discarded" as ItemStatus }) ?? p.items)
                : (listOps.remove(p.items, itemId) ?? p.items),
            })),
          ),
      },
    ],
    onError: (error: Error) => {
      toast.error("Erro ao remover conteúdo", { description: error.message });
    },
  });
}

export function useReorderPlanItems() {
  return useCacheWriteMutation<PlanItem[], { planId: string; ids: string[] }>({
    mutationFn: ({ planId, ids }) =>
      api.put<PlanItem[]>(`/api/content/plans/${planId}/items/order`, { ids }),
    targets: ({ planId }) => [
      {
        ...PLANS,
        commit: (old: PlansPage | undefined, ordered) =>
          listOps.within(old, "items", (plans) =>
            listOps.update(plans, planId, (p: ContentPlan) => ({ ...p, items: ordered })),
          ),
      },
    ],
    onError: (error: Error) => {
      toast.error("Erro ao reordenar conteúdos", { description: error.message });
    },
  });
}

export function useCreateTasksFromItems() {
  const queryClient = useQueryClient();
  return useMutation({ // noc-allow: invalidate-only — the answer is only counters + task ids; which items became tasks (and their new status) is decided server-side per item
    mutationFn: ({ planId, itemIds }: { planId: string; itemIds: string[] }) =>
      api.post<{ created: number; skipped: number; failed: number; task_ids: string[] }>(
        `/api/content/plans/${planId}/tasks`,
        { item_ids: itemIds },
      ),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: [KEY] });
      queryClient.invalidateQueries({ queryKey: ["orbity-tasks"] });
      if (res.created === 0) {
        toast.info("Nenhuma tarefa criada", {
          description: "Os conteúdos selecionados já viraram tarefa ou foram descartados.",
        });
      } else if (res.failed > 0) {
        toast.warning(`${res.created} tarefa(s) criada(s)`, { description: `${res.failed} conteúdo(s) tiveram erro.` });
      } else {
        toast.success(`${res.created} tarefa(s) criada(s)!`);
      }
    },
    onError: (error: Error) => {
      toast.error("Erro ao criar tarefas", { description: error.message });
    },
  });
}

export function usePromoteItemToPost() {
  return useCacheWriteMutation<Post, { planId: string; itemId: string }>({
    mutationFn: ({ planId, itemId }) =>
      api.post<Post>(`/api/content/plans/${planId}/items/${itemId}/post`, {}),
    targets: ({ planId, itemId }) => [
      {
        ...PLANS,
        commit: (old: PlansPage | undefined, post) =>
          listOps.within(old, "items", (plans) =>
            listOps.update(plans, planId, (p: ContentPlan) => ({
              ...p,
              items: listOps.patch(p.items, itemId, { post_id: post.id }) ?? p.items,
            })),
          ),
      },
    ],
    // The new draft post appears in the posts lists, whose order/filters the server owns.
    invalidate: [["content-posts"]],
    onSuccess: () => {
      toast.success("Post criado como rascunho — siga em Posts para enviar à aprovação.");
    },
    onError: (error: Error) => {
      toast.error("Erro ao criar post", { description: error.message });
    },
  });
}

/** Preview only — the backend persists nothing; the caller appends the chosen items. */
export function useGenerateAIItems() {
  return useMutation({ // noc-allow: invalidate-only — preview only: the backend persists nothing, so there is no cached read to write
    mutationFn: ({ planId, params }: { planId: string; params: AIGenerateParams }) =>
      api.post<{ items: AIGeneratedItem[] }>(`/api/content/plans/${planId}/ai-items`, params),
  });
}
