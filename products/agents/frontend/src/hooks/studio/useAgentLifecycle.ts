/**
 * Agent lifecycle — the same routes the `noctus.agents.content` MCP chat drives:
 *   POST   /api/studio/plataforma/agents   { key }  -> 201 (idempotent; 422 chave_nao_registrada)
 *   DELETE /api/studio/agents/{key}                 -> 204 (409 publicado|tem_instancias|tem_conversas|tem_canal|ativo)
 */
import { useQueryClient } from "@tanstack/react-query";
import { useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { api } from "@/lib/api";
import type { AgentListResponse, AgentSummary } from "@/api/studio/types";
import { seg, studioKeys } from "./keys";

export interface PlatformAgentCreated {
  id: string;
  key: string;
  org_id: string;
  definition_scope: string;
  conteudo_modo: string;
}

export function useCreatePlatformAgent() {
  return useCacheWriteMutation<PlatformAgentCreated, { key: string }>({
    mutationFn: (payload) => api.post<PlatformAgentCreated>("/api/studio/plataforma/agents", payload),
    targets: [
      {
        queryKey: studioKeys.list(),
        // The 201 body is a stub, not a full summary: the row shows what is known (empty shell, name = key) and
        // the background settle refetch fills nome/versões. Idempotent create: never duplicate an existing key.
        commit: (old: AgentListResponse | undefined, created) => {
          if (!old || old.items.some((a) => a.key === created.key)) return old;
          const row: AgentSummary = {
            id: created.id,
            key: created.key,
            nome: created.key,
            descricao: null,
            definition_mode: "studio",
            ativo: false,
            publicacao_limiar: 0,
            versao_ativa: null,
            tem_rascunho: false,
            kind: "runtime",
            definition_scope: created.definition_scope as AgentSummary["definition_scope"],
            conteudo_modo: created.conteudo_modo as AgentSummary["conteudo_modo"],
          };
          return { ...old, items: [...old.items, row] };
        },
      },
    ],
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
