/**
 * Agent lifecycle — the same routes the `noctus.agents.content` MCP chat drives:
 *   POST   /api/studio/plataforma/agents   { key }  -> 201 (idempotent; 422 chave_nao_registrada)
 *   DELETE /api/studio/agents/{key}                 -> 204 (409 publicado|tem_instancias|tem_conversas|tem_canal|ativo)
 */
import { useQueryClient } from "@tanstack/react-query";
import { useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { api } from "@/lib/api";
import type { AgentListResponse } from "@/api/studio/types";
import { seg, studioKeys } from "./keys";

export interface PlatformAgentCreated {
  id: string;
  key: string;
  org_id: string;
  definition_scope: string;
  conteudo_modo: string;
}

export function useCreatePlatformAgent() {
  // The 201 body is not a full list summary (no nome/versões), so there is nothing honest to write into the list:
  // the list target is refreshed in the background and the caller navigates straight to the new agent.
  return useCacheWriteMutation<PlatformAgentCreated, { key: string }>({
    mutationFn: (payload) => api.post<PlatformAgentCreated>("/api/studio/plataforma/agents", payload),
    targets: [{ queryKey: studioKeys.list() }],
  });
}

export function useDeleteStudioAgent() {
  const qc = useQueryClient();
  return useCacheWriteMutation<unknown, string>({
    mutationFn: (key) => api.delete(`/api/studio/agents/${seg(key)}`),
    // The row leaves the list at once; a 409 rolls it back and the server's reason is shown.
    targets: (key) => [
      {
        queryKey: studioKeys.list(),
        optimistic: (old: AgentListResponse | undefined) =>
          old ? { ...old, items: old.items.filter((a) => a.key !== key) } : undefined,
      },
    ],
    onSuccess: (_d, key) => qc.removeQueries({ queryKey: studioKeys.agent(key) }),
  });
}
