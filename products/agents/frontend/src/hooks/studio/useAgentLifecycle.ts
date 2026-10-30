/**
 * Agent lifecycle — the same routes the `noctus.agents.content` MCP chat drives:
 *   POST   /api/studio/plataforma/agents   { key }  -> 201 (idempotent; 422 chave_nao_registrada)
 *   DELETE /api/studio/agents/{key}                 -> 204 (409 publicado|tem_instancias|tem_conversas|tem_canal|ativo)
 */
import { useQueryClient } from "@tanstack/react-query";
import { useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { api } from "@/lib/api";
import type { AgentePainel, AgentesPainelResponse } from "@/api/agentes/types";
import type { AgentListResponse, AgentSummary } from "@/api/studio/types";
import { AGENTES_PAINEL_KEY, agentePainelKey } from "@/hooks/useAgentesPainel";
import type { Briefing, GeracaoOut } from "@/api/studio/types-geracao";
import { seg, studioKeys } from "./keys";

export interface PlatformAgentCreated {
  id: string;
  key: string;
  org_id: string;
  definition_scope: string;
  conteudo_modo: string;
  nome?: string;
  descricao?: string | null;
  runtime?: string;
  owner_product?: string | null;
  usa_canais?: boolean;
  instanciavel?: boolean;
  papel?: "gerador" | "exemplar" | null;
  /** S3a: non-null iff a briefing was sent. */
  geracao?: GeracaoOut | null;
}

/** CONTRACT §6 create body (`PlataformaAgentCreateRequest`); the wizard builds it from the model's fields. */
export interface PlatformAgentInput {
  key: string;
  nome?: string;
  descricao?: string;
  runtime?: string;
  owner_product?: string;
  escopo_qualificacao?: string;
  padrao_qualificacao?: string;
  briefing?: Briefing;
  limite_usd?: number;
  /** "Disponível para as organizações" (API default false). */
  instanciavel?: boolean;
}

/** The painel card the 201 lets us draw at once; the settle refetch replaces it with the server's own card
 * (catalogue description, capabilities and the exact section list THIS caller may open). */
export function painelDoCriado(created: PlatformAgentCreated, vars: PlatformAgentInput): AgentePainel {
  return {
    key: created.key,
    nome: created.nome ?? vars.nome ?? created.key,
    descricao: created.descricao ?? vars.descricao ?? null,
    papel: null,
    capacidades: [],
    origem: "plataforma",
    tipo: "runtime",
    runtime: created.runtime ?? vars.runtime ?? "llm",
    owner_product: created.owner_product ?? vars.owner_product ?? null,
    usa_canais: created.usa_canais ?? false,
    ativo: false,
    estado_externo: null,
    aviso: null,
    secoes: ["visao-geral"],
    pode_alternar: false,
  };
}

export function useCreatePlatformAgent() {
  const qc = useQueryClient();
  return useCacheWriteMutation<PlatformAgentCreated, PlatformAgentInput>({
    mutationFn: (payload) => api.post<PlatformAgentCreated>("/api/studio/plataforma/agents", payload),
    // A briefing starts a run: seed the agent page's run list so the panel opens on it at once.
    onSuccess: (created) => {
      if (created.geracao) qc.setQueryData(studioKeys.geracoes(created.key), { items: [created.geracao] });
    },
    targets: (vars) => [
      {
        // The unified listing (`/agentes`) shows the new card at once; never a duplicate of an existing key.
        queryKey: AGENTES_PAINEL_KEY,
        commit: (old: AgentesPainelResponse | undefined, created, vars) => {
          if (!old || old.items.some((a) => a.key === created.key)) return old;
          return { items: [...old.items, painelDoCriado(created, vars)], total: old.total + 1 };
        },
      },
      {
        // The page header the wizard navigates to (`/agentes/:key`) renders without a round trip.
        queryKey: agentePainelKey(vars.key),
        commit: (old: AgentePainel | undefined, created: PlatformAgentCreated) => old ?? painelDoCriado(created, vars),
      },
      {
        queryKey: studioKeys.list(),
        // The 201 body is a stub, not a full summary: the row shows what is known (empty shell, name = key) and
        // the background settle refetch fills nome/versões. Idempotent create: never duplicate an existing key.
        commit: (old: AgentListResponse | undefined, created, vars) => {
          if (!old || old.items.some((a) => a.key === created.key)) return old;
          const row: AgentSummary = {
            id: created.id,
            key: created.key,
            nome: vars.nome ?? created.key,
            descricao: null,
            definition_mode: "studio",
            ativo: false,
            publicacao_limiar: 0,
            versao_ativa: null,
            tem_rascunho: false,
            kind: "runtime",
            usa_canais: created.usa_canais ?? false,
            runtime: created.runtime,
            owner_product: created.owner_product ?? null,
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
      {
        // The card leaves the unified listing at once too (`/agentes`).
        queryKey: AGENTES_PAINEL_KEY,
        optimistic: (old: AgentesPainelResponse | undefined) =>
          old && old.items.some((a) => a.key === key)
            ? { items: old.items.filter((a) => a.key !== key), total: Math.max(0, old.total - 1) }
            : undefined,
      },
    ],
    onSuccess: (_d, key) => {
      qc.removeQueries({ queryKey: studioKeys.agent(key) });
      qc.removeQueries({ queryKey: agentePainelKey(key), exact: true });
    },
  });
}
