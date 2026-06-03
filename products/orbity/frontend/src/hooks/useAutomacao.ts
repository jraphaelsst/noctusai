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
  lead_id: string;
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
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: FlowCreate) => {
      return api.post<Flow>("/api/automation/flows", data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["automation-flows"] });
      toast.success("Fluxo criado com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao criar fluxo", { description: error.message });
    },
  });
}

export function useUpdateFlow() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: FlowUpdate & { id: string }) => {
      return api.patch<Flow>(`/api/automation/flows/${id}`, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["automation-flows"] });
      toast.success("Fluxo atualizado com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao atualizar fluxo", { description: error.message });
    },
  });
}

export function useDeleteFlow() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      return api.delete<{ ok: boolean; id: string }>(
        `/api/automation/flows/${id}`,
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["automation-flows"] });
      queryClient.invalidateQueries({ queryKey: ["automation-executions"] });
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
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: StepCreate) => {
      return api.post<Step>(`/api/automation/flows/${flowId}/steps`, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["automation-steps", flowId] });
      toast.success("Passo adicionado!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao adicionar passo", { description: error.message });
    },
  });
}

export function useUpdateStep() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      stepId,
      flowId,
      ...data
    }: StepUpdate & { stepId: string; flowId: string }) => {
      return api.patch<Step>(`/api/automation/steps/${stepId}`, data);
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: ["automation-steps", variables.flowId],
      });
      toast.success("Passo atualizado!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao atualizar passo", { description: error.message });
    },
  });
}

export function useDeleteStep() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      stepId,
      flowId,
    }: {
      stepId: string;
      flowId: string;
    }) => {
      return api.delete<{ ok: boolean; id: string }>(
        `/api/automation/steps/${stepId}`,
      );
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: ["automation-steps", variables.flowId],
      });
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
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      flowId,
      ...payload
    }: TriggerRequest & { flowId: string }) => {
      return api.post<Execution>(
        `/api/automation/flows/${flowId}/trigger`,
        payload,
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["automation-executions"] });
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
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (executionId: string) => {
      return api.delete<{ ok: boolean; id: string }>(
        `/api/automation/executions/${executionId}`,
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["automation-executions"] });
      toast.success("Execucao cancelada!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao cancelar execucao", { description: error.message });
    },
  });
}

// ---------------------------------------------------------------------------
// Run-due
// ---------------------------------------------------------------------------

export function useRunDue() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      return api.post<RunDueResult>("/api/automation/run-due", {});
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["automation-executions"] });
      toast.success(
        `Processadas ${data.processed} acoes — ${data.sent} enviadas, ${data.skipped} ignoradas, ${data.failed} falhas.`,
      );
    },
    onError: (error: Error) => {
      toast.error("Erro ao processar acoes pendentes", {
        description: error.message,
      });
    },
  });
}
