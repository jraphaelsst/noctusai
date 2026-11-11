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
import { useQuery } from "@tanstack/react-query";
import { useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { api } from "@/lib/api";
import type { Controle, ControlePlataforma, ControlePlataformaUpdate, ControleUpdate } from "@/api/studio/types-julia";
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
  return useCacheWriteMutation<Controle, ControleUpdate>({
    mutationFn: (payload) => api.put<Controle>(`/api/studio/agents/${seg(key)}/controle`, payload),
    // The server's answer is the new state; the evaluation flags are predictable, so it is drawn at once.
    targets: [
      {
        queryKey: studioKeys.controle(key),
        optimistic: (old: Controle | undefined, v: ControleUpdate) => {
          if (!old || v.modo !== old.modo) return old;
          const { modo: _modo, dreno_inatividade_dias: _d, ...resto } = v as ControleUpdate & { dreno_inatividade_dias?: number };
          const next = { ...old, ...resto };
          // Only the ids are predictable; names/phones come from the server's answer (commit below).
          if (v.avaliacao_usuarios) {
            next.avaliacao_resolvidos = (old.avaliacao_resolvidos ?? []).filter((r) => v.avaliacao_usuarios!.includes(r.usuario_id));
          }
          return next;
        },
        commit: (_old, saved) => saved,
      },
    ],
    invalidate: [studioKeys.orgStatus(key), studioKeys.list(), studioKeys.prontidao(key)],
  });
}

/** Platform kill switch (platform admin only; any other caller gets 403 -> error state, never shown). */
export function useControlePlataforma(key: string, enabled: boolean) {
  const q = useQuery<ControlePlataforma>({
    queryKey: studioKeys.controlePlataforma(key),
    queryFn: () => api.get<ControlePlataforma>(`/api/studio/plataforma/agentes/${seg(key)}/controle`),
    enabled: !!key && enabled,
    retry: false,
    placeholderData: keepWithinAgent<ControlePlataforma>(key),
  });
  return toView(q);
}

export function useSetControlePlataforma(key: string) {
  return useCacheWriteMutation<ControlePlataforma, ControlePlataformaUpdate>({
    mutationFn: (payload) => api.put<ControlePlataforma>(`/api/studio/plataforma/agentes/${seg(key)}/controle`, payload),
    targets: [{ queryKey: studioKeys.controlePlataforma(key), commit: (_old, saved) => saved }],
    invalidate: [studioKeys.controle(key)],
  });
}
