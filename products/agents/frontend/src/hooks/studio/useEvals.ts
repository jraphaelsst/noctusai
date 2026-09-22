/**
 * Eval hooks — Agent Studio CONTRACT.md §D4.
 *
 * Cases are agent-scoped CRUD; runs are created against a `version_id` and
 * polled while in flight — no SSE stream is defined for runs (§D4 is REST
 * only), so `refetchInterval` is the correct mechanism here (unlike
 * `KB § PATTERNS/frontend/inbox-chat-surface.md`'s "never refetchInterval",
 * which is scoped to chat/inbox surfaces that DO have a realtime stream).
 * Mirrors `products/erp-imobiliario/frontend/src/hooks/useCertidoes.ts`'s
 * `refetchInterval: (query) => status-in-flight ? 3000 : false` convention.
 *
 * `studioKeys.detail` (`AgentDetail.versoes[].eval_score`) reflects the
 * latest concluded run's score, so it is invalidated on every event that can
 * move it: run created (a version's "current" run changes), cancelled, and
 * — since a run only reaches a terminal status through polling, not a
 * mutation response — the transition a `useEvalRun` poll observes into
 * `concluida`/`falhou`/`cancelada`.
 */
import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  EvalCase,
  EvalCaseCreate,
  EvalCaseListResponse,
  EvalCasePatch,
  EvalRun,
  EvalRunCreate,
  EvalRunDetail,
  EvalRunListResponse,
} from "@/api/studio/types-ke";
import { studioKeys } from "./keys";

const casesKey = (agentKey: string) => ["studio", agentKey, "evals", "cases"] as const;
const runsKey = (agentKey: string, versionId?: string) => ["studio", agentKey, "evals", "runs", versionId ?? null] as const;
const runKey = (agentKey: string, runId: string) => ["studio", agentKey, "evals", "runs", "detail", runId] as const;

const IN_FLIGHT = new Set(["pendente", "executando"]);

// ─── Cases ──────────────────────────────────────────────────────────────────

export function useEvalCases(agentKey: string) {
  const query = useQuery<EvalCaseListResponse>({
    queryKey: casesKey(agentKey),
    queryFn: () => api.get<EvalCaseListResponse>(`/api/studio/agents/${agentKey}/evals/cases`),
    enabled: !!agentKey,
  });

  return {
    data: query.data?.items,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
    isError: query.isError,
    error: query.error,
  };
}

export function useCreateEvalCase(agentKey: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: EvalCaseCreate) => api.post<EvalCase>(`/api/studio/agents/${agentKey}/evals/cases`, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: casesKey(agentKey) }),
  });
}

export function useUpdateEvalCase(agentKey: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ caseId, patch }: { caseId: string; patch: EvalCasePatch }) =>
      api.patch<EvalCase>(`/api/studio/agents/${agentKey}/evals/cases/${caseId}`, patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: casesKey(agentKey) }),
  });
}

export function useDeleteEvalCase(agentKey: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (caseId: string) => api.delete(`/api/studio/agents/${agentKey}/evals/cases/${caseId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: casesKey(agentKey) }),
  });
}

// ─── Runs ───────────────────────────────────────────────────────────────────

export function useEvalRuns(agentKey: string, versionId?: string) {
  const query = useQuery<EvalRunListResponse>({
    queryKey: runsKey(agentKey, versionId),
    queryFn: () => api.get<EvalRunListResponse>(`/api/studio/agents/${agentKey}/evals/runs`, { version_id: versionId }),
    enabled: !!agentKey,
    refetchInterval: (q) => {
      const data = q.state.data as EvalRunListResponse | undefined;
      return data?.items.some((r) => IN_FLIGHT.has(r.status)) ? 3000 : false;
    },
  });

  return {
    data: query.data?.items,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
    isError: query.isError,
  };
}

/** Run detail — polls every 3s while `status` is `pendente`/`executando` (contract §G "Avaliações": "run detail ... polling while executando"). */
export function useEvalRun(agentKey: string, runId: string | null) {
  const qc = useQueryClient();
  const query = useQuery<EvalRunDetail>({
    queryKey: runKey(agentKey, runId ?? ""),
    queryFn: () => api.get<EvalRunDetail>(`/api/studio/agents/${agentKey}/evals/runs/${runId}`),
    enabled: !!agentKey && !!runId,
    refetchInterval: (q) => {
      const data = q.state.data as EvalRunDetail | undefined;
      return data && IN_FLIGHT.has(data.status) ? 3000 : false;
    },
  });

  // v5 dropped `useQuery({ onSuccess })` — a completion is observed here,
  // client-side, the moment a poll sees a terminal status (see file header).
  const notifiedFor = useRef<string | null>(null);
  const status = query.data?.status;
  useEffect(() => {
    if (!runId || !status || IN_FLIGHT.has(status)) return;
    if (notifiedFor.current === runId) return;
    notifiedFor.current = runId;
    qc.invalidateQueries({ queryKey: studioKeys.detail(agentKey) });
  }, [agentKey, qc, runId, status]);

  return {
    data: query.data,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
    isError: query.isError,
    error: query.error,
  };
}

export function useCreateEvalRun(agentKey: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: EvalRunCreate) => api.post<EvalRun>(`/api/studio/agents/${agentKey}/evals/runs`, payload),
    onSuccess: (run) => {
      qc.invalidateQueries({ queryKey: ["studio", agentKey, "evals", "runs"] });
      qc.invalidateQueries({ queryKey: studioKeys.detail(agentKey) });
      qc.setQueryData(runKey(agentKey, run.id), { ...run, resultados: [] });
    },
  });
}

export function useCancelEvalRun(agentKey: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => api.post<EvalRun>(`/api/studio/agents/${agentKey}/evals/runs/${runId}/cancel`),
    onSuccess: (run) => {
      qc.invalidateQueries({ queryKey: ["studio", agentKey, "evals", "runs"] });
      qc.invalidateQueries({ queryKey: studioKeys.detail(agentKey) });
      qc.setQueryData(runKey(agentKey, run.id), (prev: EvalRunDetail | undefined) =>
        prev ? { ...prev, ...run } : prev,
      );
    },
  });
}
