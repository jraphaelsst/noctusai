/**
 * Agent Studio — the mechanism suite as a queued job (`KB § PATTERNS/frontend/mutation-cache-writes.md`, "a queued
 * job hands off"):
 *
 *   POST /api/studio/agents/{key}/draft/mecanismo-runs      -> 202 {run_id, status: "executando"} (platform admin)
 *   GET  /api/studio/agents/{key}/mecanismo-runs/{run_id}   -> executando | concluida | falhou | cancelada
 *
 * The POST hands the booked run to the run query (seeded as `executando`, so the UI never flashes empty); the GET
 * polls every 3s while in flight; the poll that first sees a terminal status refetches the readiness checklist and
 * the agent detail (the verdict the suite moved), exactly once per run.
 */
import { useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { api } from "@/lib/api";
import type { MecanismoRun, MecanismoRunIniciada } from "@/api/studio/types-prontidao";
import { seg, studioKeys, toView } from "./keys";

const mecanismoRunKey = (key: string, runId: string) => ["studio", key, "mecanismo-run", runId] as const;

export function useIniciarMecanismo(key: string) {
  const qc = useQueryClient();
  return useCacheWriteMutation<MecanismoRunIniciada, void>({
    mutationFn: () => api.post<MecanismoRunIniciada>(`/api/studio/agents/${seg(key)}/draft/mecanismo-runs`),
    targets: [],
    onSuccess: (run) => {
      qc.setQueryData<MecanismoRun>(mecanismoRunKey(key, run.run_id), (old) =>
        old ?? {
          run_id: run.run_id, version_id: "", compiled_hash: run.compiled_hash, driver: run.driver,
          status: "executando", aprovado: false, completo: false, orcamento_excedido: false, custo_usd: null,
          total_casos: 0, casos_aprovados: 0, erro: null, casos: [],
        });
    },
  });
}

export function useMecanismoRun(key: string, runId: string | null) {
  const qc = useQueryClient();
  const q = useQuery<MecanismoRun>({
    queryKey: mecanismoRunKey(key, runId ?? ""),
    queryFn: () => api.get<MecanismoRun>(`/api/studio/agents/${seg(key)}/mecanismo-runs/${seg(runId ?? "")}`),
    enabled: !!key && !!runId,
    retry: false,
    refetchInterval: (query) => {
      if (query.state.status === "error") return false;
      const s = (query.state.data as MecanismoRun | undefined)?.status;
      return s === undefined || s === "executando" ? 3000 : false;
    },
  });
  const settledFor = useRef<string | null>(null);
  const status = q.data?.status;
  useEffect(() => {
    if (!runId || !status || status === "executando" || settledFor.current === runId) return;
    settledFor.current = runId;
    void qc.invalidateQueries({ queryKey: studioKeys.prontidao(key) });
    void qc.invalidateQueries({ queryKey: studioKeys.detail(key) });
  }, [key, qc, runId, status]);
  return toView(q);
}
