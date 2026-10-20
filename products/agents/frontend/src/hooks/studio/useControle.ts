/**
 * Agent Studio — the agent's controls (CONTRACT §5; `channel_threads_router.py`).
 *
 *   GET /api/studio/agents/{key}/controle   (any member)
 *   PUT /api/studio/agents/{key}/controle   (org admin) — 409 `conteudo_incompleto` /
 *                                           `llm_nao_configurado` / `no_active_version`
 *
 * The turn endpoint is what DECIDES per message; this is only the switch and the drain progress.
 * The state shown is always the last server answer, never a local copy.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Controle, ControleUpdate } from "@/api/studio/types-julia";
import { keepWithinAgent, seg, studioKeys, toView } from "./keys";

export function useControle(key: string, enabled = true) {
  const q = useQuery<Controle>({
    queryKey: studioKeys.controle(key),
    queryFn: () => api.get<Controle>(`/api/studio/agents/${seg(key)}/controle`),
    enabled: !!key && enabled,
    retry: false,
    placeholderData: keepWithinAgent<Controle>(key),
  });
  return toView(q);
}

export function useSetControle(key: string) {
  const qc = useQueryClient();
  return useMutation<Controle, unknown, ControleUpdate>({
    mutationFn: (payload) => api.put<Controle>(`/api/studio/agents/${seg(key)}/controle`, payload),
    onSuccess: (controle) => {
      qc.setQueryData(studioKeys.controle(key), controle);
      void qc.invalidateQueries({ queryKey: studioKeys.controle(key) });
      void qc.invalidateQueries({ queryKey: studioKeys.orgStatus(key) });
      void qc.invalidateQueries({ queryKey: studioKeys.list() });
    },
  });
}
