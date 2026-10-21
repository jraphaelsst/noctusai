/**
 * Automacao hooks for Orbity — WhatsApp flow engine: flows, steps, executions, run-due.
 *
 * API contract mirrors backend schemas/automation.py:
 *   Flow:      id, org_id, name, trigger_type, trigger_config, active,
 *              schedule_window, stop_rules, created_at, updated_at
 *   Step:      id, org_id, flow_id, ord, step_type, config, created_at, updated_at
 *   Execution: id, org_id, flow_id, lead_id, status, current_step_ord,
 *              started_at, next_action_at, context, error_detail, created_at, updated_at
 *   RunDue:    processed, sent, skipped, failed
 *
 * Nav route key: "automacao" — requires a status_pagina row with page_key = "automacao".
 *
 * Convention: one file per domain entity, TanStack Query throughout.
 * `api` is imported from `@/lib/api` (the local seam).
 */
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuthStore } from "@noctusai/seed/infra";

// ---------------------------------------------------------------------------
// Domain types (mirrors backend schemas/automation.py)
// ---------------------------------------------------------------------------

export type TriggerType =
  | "lead_created"
  | "pipeline_stage_entered"
  | "lead_idle"
  | "whatsapp_message_received"
  | "keyword_received"
  | "tag_added"
  | "owner_changed"
  | "task_created"
  | "task_completed"
  | "meeting_created"
  | "proposal_sent"
  | "client_created"
  | "lead_status_changed"
  | "manual";

export type StepType =
  | "send_message"
  | "send_whatsapp_media"
  | "wait"
  | "condition"
  | "action"
  | "branch"
  | "end";

export type ExecutionStatus = "running" | "done" | "canceled" | "failed";
export type SubjectType = "lead" | "client" | "task" | "meeting";

export interface Flow {
  id: string;
  org_id: string;
  name: string;
  trigger_type: TriggerType;
  trigger_config: Record<string, unknown>;
  active: boolean;
  schedule_window: Record<string, unknown>;
  stop_rules: Record<string, unknown>;
  created_at: string | null;
  updated_at: string | null;
}

export interface Step {
  id: string;
  org_id: string;
  flow_id: string;
  ord: number;
  step_type: StepType;
  config: Record<string, unknown>;
  created_at: string | null;
  updated_at: string | null;
}

export interface Execution {
  id: string;
  org_id: string;
  flow_id: string;
  /** Null for task/client/meeting runs (those carry subject_id). */
  lead_id: string | null;
  subject_type?: SubjectType | string;
  subject_id?: string | null;
  trigger_key?: string | null;
  status: ExecutionStatus;
  current_step_ord: number;
  started_at: string | null;
  next_action_at: string | null;
  context: Record<string, unknown>;
  error_detail: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface RunDueResult {
  processed: number;
  sent: number;
  skipped: number;
  failed: number;
}

// ---------------------------------------------------------------------------
// Inbound create/update types
// ---------------------------------------------------------------------------

export interface FlowCreate {
  name: string;
  trigger_type: TriggerType;
  trigger_config?: Record<string, unknown>;
  active?: boolean;
  schedule_window?: Record<string, unknown>;
  stop_rules?: Record<string, unknown>;
}

export interface FlowUpdate {
  name?: string;
  trigger_type?: TriggerType;
  trigger_config?: Record<string, unknown>;
  active?: boolean;
  schedule_window?: Record<string, unknown>;
  stop_rules?: Record<string, unknown>;
}

export interface StepCreate {
  ord: number;
  step_type: StepType;
  config?: Record<string, unknown>;
}

export interface StepUpdate {
  ord?: number;
  step_type?: StepType;
  config?: Record<string, unknown>;
}

export interface TriggerRequest {
  lead_id: string;
  context?: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Flows
// ---------------------------------------------------------------------------

export function useFlows(activeOnly = false) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["automation-flows", activeOnly],
    queryFn: async () => {
      return api.get<Flow[]>("/api/automation/flows", {
        active_only: activeOnly,
      });
    },
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
  });
}

export function useCreateFlow() {
  // Flows come back oldest-first (created_at asc): the new flow goes last, in the
  // unfiltered list and — when it is active — in the active-only one.
  return useCacheWriteMutation<Flow, FlowCreate>({
    mutationFn: async (data) => {
      return api.post<Flow>("/api/automation/flows", data);
    },
    targets: [
      {
        queryKey: ["automation-flows", false],
        commit: (old: Flow[] | undefined, saved) => listOps.replace(old, saved.id, saved),
      },
      {
        queryKey: ["automation-flows", true],
        commit: (old: Flow[] | undefined, saved) => (saved.active ? listOps.replace(old, saved.id, saved) : old),
      },
    ],
    onSuccess: () => {
      toast.success("Fluxo criado com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao criar fluxo", { description: error.message });
    },
  });
}

export function useUpdateFlow() {
  return useCacheWriteMutation<Flow, FlowUpdate & { id: string }>({
    mutationFn: async ({ id, ...data }) => {
      return api.patch<Flow>(`/api/automation/flows/${id}`, data);
    },
    // Every cached flows list gets the server's row; an active-only list that
    // the edit pushed out of (or into) the filter converges on the settle.
    targets: [
      {
        queryKey: ["automation-flows"],
        match: "prefix",
        commit: (old: Flow[] | undefined, saved) =>
          Array.isArray(old) && old.some((f) => f.id === saved.id) ? listOps.replace(old, saved.id, saved) : old,
      },
    ],
    onSuccess: () => {
      toast.success("Fluxo atualizado com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao atualizar fluxo", { description: error.message });
    },
  });
}

export function useDeleteFlow() {
  return useCacheWriteMutation<{ ok: boolean; id: string }, string>({
    mutationFn: async (id) => {
      return api.delete<{ ok: boolean; id: string }>(
        `/api/automation/flows/${id}`,
      );
    },
    targets: [
      {
        queryKey: ["automation-flows"],
        match: "prefix",
        optimistic: (old: Flow[] | undefined, id) => listOps.remove(old, id),
      },
    ],
    // The flow's executions go with it — a derived view the client does not recompute.
    invalidate: [["automation-executions"]],
    onSuccess: () => {
      toast.success("Fluxo removido com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao remover fluxo", { description: error.message });
    },
  });
}

// ---------------------------------------------------------------------------
// Steps
// ---------------------------------------------------------------------------

export function useSteps(flowId: string | null) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["automation-steps", flowId],
    queryFn: async () => {
      return api.get<Step[]>(`/api/automation/flows/${flowId}/steps`);
    },
    enabled: !!user && !!flowId,
    staleTime: 3 * 60 * 1000,
  });
}

export function useCreateStep(flowId: string) {
  return useCacheWriteMutation<Step, StepCreate>({
    mutationFn: async (data) => {
      return api.post<Step>(`/api/automation/flows/${flowId}/steps`, data);
    },
    // Steps are listed by `ord` ascending: the new step lands at its ord.
    targets: [
      {
        queryKey: ["automation-steps", flowId],
        commit: (old: Step[] | undefined, saved) =>
          listOps.replace(old, saved.id, saved)?.sort((a, b) => a.ord - b.ord),
      },
    ],
    onSuccess: () => {
      toast.success("Passo adicionado!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao adicionar passo", { description: error.message });
    },
  });
}

export function useUpdateStep() {
  return useCacheWriteMutation<Step, StepUpdate & { stepId: string; flowId: string }>({
    mutationFn: async ({ stepId, flowId: _flowId, ...data }) => {
      return api.patch<Step>(`/api/automation/steps/${stepId}`, data);
    },
    targets: ({ flowId }) => [
      {
        queryKey: ["automation-steps", flowId],
        commit: (old: Step[] | undefined, saved) =>
          listOps.replace(old, saved.id, saved)?.sort((a, b) => a.ord - b.ord),
      },
    ],
    onSuccess: () => {
      toast.success("Passo atualizado!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao atualizar passo", { description: error.message });
    },
  });
}

export function useDeleteStep() {
  return useCacheWriteMutation<{ ok: boolean; id: string }, { stepId: string; flowId: string }>({
    mutationFn: async ({ stepId }) => {
      return api.delete<{ ok: boolean; id: string }>(
        `/api/automation/steps/${stepId}`,
      );
    },
    targets: ({ flowId }) => [
      {
        queryKey: ["automation-steps", flowId],
        optimistic: (old: Step[] | undefined, { stepId }) => listOps.remove(old, stepId),
      },
    ],
    onSuccess: () => {
      toast.success("Passo removido!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao remover passo", { description: error.message });
    },
  });
}

// ---------------------------------------------------------------------------
// Trigger
// ---------------------------------------------------------------------------

export function useTriggerFlow() {
  // Executions are listed newest first (started_at desc): the new run goes on top
  // of the unfiltered list and of the triggering lead's list.
  return useCacheWriteMutation<Execution, TriggerRequest & { flowId: string }>({
    mutationFn: async ({ flowId, ...payload }) => {
      return api.post<Execution>(
        `/api/automation/flows/${flowId}/trigger`,
        payload,
      );
    },
    targets: ({ lead_id }) => [
      {
        queryKey: ["automation-executions", undefined],
        commit: (old: Execution[] | undefined, saved) => listOps.replace(old, saved.id, saved, "prepend"),
      },
      {
        queryKey: ["automation-executions", lead_id],
        commit: (old: Execution[] | undefined, saved) => listOps.replace(old, saved.id, saved, "prepend"),
      },
    ],
    onSuccess: () => {
      toast.success("Fluxo disparado com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao disparar fluxo", { description: error.message });
    },
  });
}

// ---------------------------------------------------------------------------
// Executions
// ---------------------------------------------------------------------------

export function useExecutions(leadId?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["automation-executions", leadId],
    queryFn: async () => {
      return api.get<Execution[]>("/api/automation/executions", {
        lead_id: leadId,
      });
    },
    enabled: !!user,
    staleTime: 60 * 1000,
    refetchInterval: 30 * 1000, // poll every 30s for running executions
  });
}

export function useCancelExecution() {
  return useCacheWriteMutation<{ ok: boolean; id: string }, string>({
    mutationFn: async (executionId) => {
      return api.delete<{ ok: boolean; id: string }>(
        `/api/automation/executions/${executionId}`,
      );
    },
    targets: [
      {
        queryKey: ["automation-executions"],
        match: "prefix",
        optimistic: (old: Execution[] | undefined, executionId) =>
          listOps.patch(old, executionId, { status: "canceled" }),
      },
    ],
    onSuccess: () => {
      toast.success("Execução cancelada!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao cancelar execução", { description: error.message });
    },
  });
}

// ---------------------------------------------------------------------------
// Run-due
// ---------------------------------------------------------------------------

export function useRunDue() {
  const queryClient = useQueryClient();

  return useMutation({ // noc-allow: invalidate-only — run-due executes whatever is due server-side and returns only counters; which executions changed is unknown to the client
    mutationFn: async () => {
      return api.post<RunDueResult>("/api/automation/run-due", {});
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["automation-executions"] });
      toast.success(
        `Processadas ${data.processed} ações — ${data.sent} enviadas, ${data.skipped} ignoradas, ${data.failed} falhas.`,
      );
    },
    onError: (error: Error) => {
      toast.error("Erro ao processar ações pendentes", {
        description: error.message,
      });
    },
  });
}
