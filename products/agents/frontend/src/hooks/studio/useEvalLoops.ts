/**
 * Eval-loop hooks — products/agents/docs/eval-loop-gate-contract.md.
 *
 *   GET  /api/studio/agents/{key}/evals/loops[?suite=]       -> {items: LoopOut[]} (newest first)
 *   GET  /api/studio/agents/{key}/evals/loops/{id}           -> LoopOut
 *   POST /api/studio/agents/{key}/evals/loops                -> 201 LoopOut
 *   POST /api/studio/agents/{key}/evals/loops/{id}/stop      -> LoopOut
 *   POST /api/studio/agents/{key}/evals/loops/{id}/refinamentos/{rodada}/revisao  -> LoopOut  (platform admin: accept / revert an edit)
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
  EvalLoopModo,
  EvalLoopRefinoDecisao,
  EvalLoopSuite,
  EvalRun,
  EvalRunCreate,
} from "@/api/studio/types-ke";
import type { MecanismoRunIniciada } from "@/api/studio/types-prontidao";
import { seg, studioKeys } from "./keys";

/** Platform-level loop config route — one constant so a path change is a one-line edit. */
export const LOOP_CONFIG_PATH = "/api/studio/plataforma/eval-loop-config";
export const loopConfigKey = ["studio", "__evals__", "loop-config"] as const;

export const loopsKey = (agentKey: string) => ["studio", agentKey, "evals", "loops"] as const;
const loopsListKey = (agentKey: string, suite: EvalLoopSuite | null) =>
  [...loopsKey(agentKey), "list", suite] as const;
const loopKey = (agentKey: string, loopId: string) => [...loopsKey(agentKey), "detail", loopId] as const;

/** True while any round of the loop is still being measured. */
export function hasRoundInFlight(loop: EvalLoop | undefined): boolean {
  return !!loop && loop.status === "ativo" && loop.serie.some((r) => r.status === "executando");
}

/** The loop's own state keeps moving without any click: a round is open, or an AUTOMATIC loop is between rounds (the server
 * books the next one by itself). Only then is it polled; a manual / idle / ended loop is read once and left alone. */
export function loopIsMoving(loop: EvalLoop | undefined): boolean {
  if (!loop || loop.status !== "ativo") return false;
  return hasRoundInFlight(loop) || loop.estado_driver === "rodando" || loop.estado_driver === "automatico";
}

const POLL_MS = 2000;

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
    // poll-budget: 3s only while a loop round is in flight, stops when none is; 1 calls/tick (refetch of the polled GET, only while the job is in flight); worst 28800/day per open tab; hidden=paused
    refetchInterval: (q) => {
      const data = q.state.data as EvalLoopListResponse | undefined;
      return data?.items.some(loopIsMoving) ? POLL_MS : false;
    },
  });
  const items = query.data?.items;
  useSettleOnRoundClose(agentKey, !!items?.some(loopIsMoving));
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
    // poll-budget: 3s only while this loop's round is in flight, stops after; 1 calls/tick (refetch of the polled GET, only while the job is in flight); worst 28800/day per open tab; hidden=paused
    refetchInterval: (q) => (loopIsMoving(q.state.data as EvalLoop | undefined) ? POLL_MS : false),
  });
  useSettleOnRoundClose(agentKey, loopIsMoving(query.data));
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

/** Put a just-booked round into every cached copy of its loop as an OPEN round: the write fills every entry it touches,
 * so the panel shows "rodada em andamento" at once and the poll that follows is already armed (the stale "Rodada 0" the
 * owner saw came from a start that left the loop caches untouched). The server's next read replaces it. */
function withOpenRound(loop: EvalLoop, runId: string): EvalLoop {
  if (loop.status !== "ativo" || loop.serie.some((r) => r.run_id === runId)) return loop;
  return {
    ...loop,
    estado_driver: "rodando",
    aviso: null,
    serie: [
      ...loop.serie,
      {
        rodada: loop.serie.length + 1,
        run_id: runId,
        status: "executando",
        score: null,
        custo_usd: 0,
        compiled_hash: null,
        melhorou: null,
        overcall: false,
        falhas: [],
      },
    ],
  };
}

/** One round: a whole-suite run stamped with the loop. The run's answer carries its id, so the round is written into the
 * loop caches as open (see `withOpenRound`) and the server closes it later; the polls then settle the real numbers. */
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
    onSuccess: (data, { loopId }) => {
      const runId = "run_id" in data ? data.run_id : data.id;
      qc.setQueriesData<EvalLoopListResponse>({ queryKey: [...loopsKey(agentKey), "list"] }, (old) =>
        old ? { ...old, items: old.items.map((l) => (l.id === loopId ? withOpenRound(l, runId) : l)) } : old,
      );
      qc.setQueryData<EvalLoop>(loopKey(agentKey, loopId), (old) => (old ? withOpenRound(old, runId) : old));
      void qc.refetchQueries({ queryKey: loopsKey(agentKey) });
    },
  });
}

/** Pause (`manual`) or resume (`automatico`) the driver. The server's `LoopOut` goes into every entry the loop lives in. */
export function useSetLoopModo(agentKey: string) {
  const qc = useQueryClient();
  return useCacheWriteMutation<EvalLoop, { loopId: string; modo: EvalLoopModo }>({
    mutationFn: ({ loopId, modo }) =>
      api.put<EvalLoop>(`/api/studio/agents/${seg(agentKey)}/evals/loops/${seg(loopId)}/modo`, { modo }),
    targets: loopWriteTargets(agentKey, replaceInPlace),
    onSuccess: (loop) => {
      qc.setQueryData(loopKey(agentKey, loop.id), loop);
    },
  });
}

/** Accept or revert the edit the refine step wrote into the draft after round `rodada`. The server's `LoopOut` goes into every loop entry;
 * a revert rewrote a draft row and an accept/revert clears the publish gate, so what derives from the draft is queued to refetch
 * (readiness, the draft and its compiled prompt) -- the server owns those answers. */
export function useReviewRefinamento(agentKey: string) {
  const qc = useQueryClient();
  return useCacheWriteMutation<EvalLoop, { loopId: string; rodada: number; decisao: EvalLoopRefinoDecisao }>({
    mutationFn: ({ loopId, rodada, decisao }) =>
      api.post<EvalLoop>(`/api/studio/agents/${seg(agentKey)}/evals/loops/${seg(loopId)}/refinamentos/${rodada}/revisao`, { decisao }),
    targets: loopWriteTargets(agentKey, replaceInPlace),
    onSuccess: (loop) => {
      qc.setQueryData(loopKey(agentKey, loop.id), loop);
      void qc.invalidateQueries({ queryKey: studioKeys.prontidao(agentKey) });
      void qc.invalidateQueries({ queryKey: studioKeys.detail(agentKey) });
      void qc.invalidateQueries({ queryKey: studioKeys.versions(agentKey) });
      void qc.invalidateQueries({ queryKey: studioKeys.compiledAll(agentKey) });
      void qc.invalidateQueries({ queryKey: studioKeys.conteudoAll(agentKey) });
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
    // The server stamps `alterado_em`: commit its answer over the single cached entry.
    targets: [{ queryKey: loopConfigKey, commit: (_old: EvalLoopConfig | undefined, saved) => saved }],
  });
}
