/**
 * Eval-loop hooks — products/agents/docs/eval-loop-gate-contract.md.
 *
 *   GET  /api/studio/agents/{key}/evals/loops[?suite=]       -> {items: LoopOut[]} (newest first)
 *   GET  /api/studio/agents/{key}/evals/loops/{id}           -> LoopOut
 *   POST /api/studio/agents/{key}/evals/loops                -> 201 LoopOut
 *   POST /api/studio/agents/{key}/evals/loops/{id}/stop      -> LoopOut
 *   round = a run started with `loop_id` (evals/runs body, or draft/mecanismo-runs?loop_id=)
 *
 * Cache writes (`KB § PATTERNS/frontend/mutation-cache-writes.md`): create/stop put the server's `LoopOut` into
 * every list entry and the detail entry they touch; starting a round queues server work (the round closes in the
 * run's close hook), so it hands off to polling — the loop read keeps polling while a round is `executando`.
 * Polling is `refetchInterval` (REST only, no stream), same IN_FLIGHT convention as `useEvals.ts`.
 */
import { useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { api } from "@/lib/api";
import type {
  EvalLoop,
  EvalLoopConfig,
  EvalLoopConfigInput,
  EvalLoopCreate,
  EvalLoopListResponse,
  EvalLoopSuite,
  EvalRun,
  EvalRunCreate,
} from "@/api/studio/types-ke";
import type { MecanismoRunIniciada } from "@/api/studio/types-prontidao";
import { seg, studioKeys } from "./keys";

/** Platform-level loop config route — one constant so a path change is a one-line edit. */
export const LOOP_CONFIG_PATH = "/api/studio/evals/loop-config";
export const loopConfigKey = ["studio", "__evals__", "loop-config"] as const;

export const loopsKey = (agentKey: string) => ["studio", agentKey, "evals", "loops"] as const;
const loopsListKey = (agentKey: string, suite: EvalLoopSuite | null) =>
  [...loopsKey(agentKey), "list", suite] as const;
const loopKey = (agentKey: string, loopId: string) => [...loopsKey(agentKey), "detail", loopId] as const;

/** True while any round of the loop is still being measured. */
export function hasRoundInFlight(loop: EvalLoop | undefined): boolean {
  return !!loop && loop.status === "ativo" && loop.serie.some((r) => r.status === "executando");
}

const POLL_MS = 3000;

/** After a round closes the score moved: refresh what derives from runs (runs list, consolidation, readiness). */
function useSettleOnRoundClose(agentKey: string, inFlight: boolean) {
  const qc = useQueryClient();
  const was = useRef(false);
  useEffect(() => {
    if (was.current && !inFlight) {
      void qc.invalidateQueries({ queryKey: ["studio", agentKey, "evals", "runs"] });
      void qc.invalidateQueries({ queryKey: ["studio", agentKey, "evals", "consolidacao"] });
      void qc.invalidateQueries({ queryKey: studioKeys.detail(agentKey) });
      void qc.invalidateQueries({ queryKey: studioKeys.prontidao(agentKey) });
    }
    was.current = inFlight;
  }, [agentKey, inFlight, qc]);
}

export function useEvalLoops(agentKey: string, suite: EvalLoopSuite | null = null, enabled = true) {
  const query = useQuery<EvalLoopListResponse>({
    queryKey: loopsListKey(agentKey, suite),
    queryFn: () =>
      api.get<EvalLoopListResponse>(`/api/studio/agents/${seg(agentKey)}/evals/loops`, suite ? { suite } : undefined),
    enabled: !!agentKey && enabled,
    refetchInterval: (q) => {
      const data = q.state.data as EvalLoopListResponse | undefined;
      return data?.items.some(hasRoundInFlight) ? POLL_MS : false;
    },
  });
  const items = query.data?.items;
  useSettleOnRoundClose(agentKey, !!items?.some(hasRoundInFlight));
  return {
    data: items,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
    isError: query.isError,
    error: query.error,
    refetch: () => void query.refetch(),
  };
}

export function useEvalLoop(agentKey: string, loopId: string | null) {
  const query = useQuery<EvalLoop>({
    queryKey: loopKey(agentKey, loopId ?? ""),
    queryFn: () => api.get<EvalLoop>(`/api/studio/agents/${seg(agentKey)}/evals/loops/${seg(loopId ?? "")}`),
    enabled: !!agentKey && !!loopId,
    refetchInterval: (q) => (hasRoundInFlight(q.state.data as EvalLoop | undefined) ? POLL_MS : false),
  });
  useSettleOnRoundClose(agentKey, hasRoundInFlight(query.data));
  return {
    data: query.data,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
    isError: query.isError,
    error: query.error,
  };
}

/** The server's `LoopOut` goes into every cached list the loop belongs to (the all-suites list or its own suite's);
 * the detail entry is written by each mutation's `onSuccess`. */
function loopWriteTargets(agentKey: string, upsert: (list: EvalLoop[], loop: EvalLoop) => EvalLoop[]) {
  return [
    {
      queryKey: [...loopsKey(agentKey), "list"],
      match: "prefix" as const,
      commit: (old: EvalLoopListResponse | undefined, saved: EvalLoop, _v: unknown, _c: unknown, key?: readonly unknown[]) => {
        const listSuite = key?.[5] as EvalLoopSuite | null | undefined;
        if (listSuite && listSuite !== saved.suite) return old;
        return listOps.within(old, "items", (l) => upsert(l as EvalLoop[], saved));
      },
    },
  ];
}

const putFirst = (l: EvalLoop[], loop: EvalLoop) => [loop, ...l.filter((x) => x.id !== loop.id)];
const replaceInPlace = (l: EvalLoop[], loop: EvalLoop) => {
  const has = l.some((x) => x.id === loop.id);
  return has ? l.map((x) => (x.id === loop.id ? loop : x)) : putFirst(l, loop);
};

export function useCreateEvalLoop(agentKey: string) {
  const qc = useQueryClient();
  return useCacheWriteMutation<EvalLoop, EvalLoopCreate>({
    mutationFn: (payload) => api.post<EvalLoop>(`/api/studio/agents/${seg(agentKey)}/evals/loops`, payload),
    // The server assigns id/alvo/piso/budget: commit only (newest first, like the list).
    targets: loopWriteTargets(agentKey, putFirst),
    onSuccess: (loop) => {
      qc.setQueryData(loopKey(agentKey, loop.id), loop);
    },
  });
}

export function useStopEvalLoop(agentKey: string) {
  const qc = useQueryClient();
  return useCacheWriteMutation<EvalLoop, { loopId: string; motivo?: string }>({
    mutationFn: ({ loopId, motivo }) =>
      api.post<EvalLoop>(
        `/api/studio/agents/${seg(agentKey)}/evals/loops/${seg(loopId)}/stop`,
        motivo ? { motivo } : {},
      ),
    targets: loopWriteTargets(agentKey, replaceInPlace),
    onSuccess: (loop) => {
      qc.setQueryData(loopKey(agentKey, loop.id), loop);
    },
  });
}

/** One round: a whole-suite run stamped with the loop. The run's answer cannot place the round in the loop (the
 * server books the round and later closes it), so the loop reads hand off to polling instead of being edited. */
export function useRunLoopRound(agentKey: string, suite: EvalLoopSuite) {
  const qc = useQueryClient();
  return useCacheWriteMutation<EvalRun | MecanismoRunIniciada, { loopId: string; versionId: string }>({
    mutationFn: ({ loopId, versionId }) =>
      suite === "mecanismo"
        ? api.post<MecanismoRunIniciada>(
            `/api/studio/agents/${seg(agentKey)}/draft/mecanismo-runs?loop_id=${encodeURIComponent(loopId)}`,
          )
        : api.post<EvalRun>(`/api/studio/agents/${seg(agentKey)}/evals/runs`, {
            version_id: versionId,
            loop_id: loopId,
          } satisfies EvalRunCreate),
    targets: [],
    invalidate: [loopsKey(agentKey), ["studio", agentKey, "evals", "runs"]],
    onSuccess: () => {
      // Keep the loop reads polling right away: the booked round shows as `executando` on the next read.
      void qc.refetchQueries({ queryKey: loopsKey(agentKey) });
    },
  });
}

export function useLoopConfig(enabled = true) {
  const query = useQuery<EvalLoopConfig>({
    queryKey: loopConfigKey,
    queryFn: () => api.get<EvalLoopConfig>(LOOP_CONFIG_PATH),
    enabled,
  });
  return {
    data: query.data,
    showSkeleton: query.isPending && !query.data && enabled,
    isError: query.isError,
    error: query.error,
    refetch: () => void query.refetch(),
  };
}

export function useUpdateLoopConfig() {
  return useCacheWriteMutation<EvalLoopConfig, EvalLoopConfigInput>({
    mutationFn: (payload) => api.put<EvalLoopConfig>(LOOP_CONFIG_PATH, payload),
    // The server stamps `atualizado_em`: commit its answer over the single cached entry.
    targets: [{ queryKey: loopConfigKey, commit: (_old: EvalLoopConfig | undefined, saved) => saved }],
  });
}
