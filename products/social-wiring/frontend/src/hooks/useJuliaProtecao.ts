/**
 * Julia > Proteção (owner 2026-10-21: "set limits and rate limitings ... so we protect our operation"): every abuse limit of the org
 * (visible and editable, with its default and range) and the per-org number blocklist.
 *
 *   GET  /api/julia/protecao/config                       → {data:{...limits, padrao, faixas, padroes, prompt_documento_padrao}}
 *   PUT  /api/julia/protecao/config {…}                   → {data: config}
 *   GET  /api/julia/protecao/bloqueios?historico          → {data:{items}}
 *   POST /api/julia/protecao/bloqueios {numero,motivo,duracao_min?}
 *   POST /api/julia/protecao/bloqueios/{id}/desbloquear
 *
 *   GET/POST/DELETE /api/julia/protecao/permitidos        the allowlist ("responder só a estes números"); the switch is `permitidos_ativo` on the config
 *
 * Loading = two signals off `data` (never `isLoading`).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { api } from "@/lib/api";

export type ChaveLimite =
  | "entrada_limite" | "entrada_janela_s" | "midia_limite_chat_dia" | "midia_limite_conexao_dia"
  | "bloqueio_auto_limiar" | "bloqueio_auto_janela_min" | "bloqueio_auto_duracao_min";

export interface ConfigProtecao {
  entrada_limite: number;
  entrada_janela_s: number;
  midia_limite_chat_dia: number;
  midia_limite_conexao_dia: number;
  bloqueio_auto_ativo: boolean;
  /** Allowlist switch: on + non-empty list = Julia answers ONLY those numbers; empty list or off = everyone. */
  permitidos_ativo?: boolean;
  bloqueio_auto_limiar: number;
  bloqueio_auto_janela_min: number;
  bloqueio_auto_duracao_min: number;
  prompt_documento_lead: string | null;
  atualizado_em: string | null;
  /** True when the org has no row yet: every value is the platform default. */
  padrao: boolean;
  faixas: Record<ChaveLimite, [number, number]>;
  padroes: Record<string, unknown>;
  prompt_documento_padrao: string;
}
export type ConfigEntrada = Partial<Omit<ConfigProtecao, "padrao" | "faixas" | "padroes" | "prompt_documento_padrao" | "prompt_documento_lead">>;

export interface Bloqueio {
  id: string;
  numero: string;
  motivo: string;
  origem: "manual" | "automatico";
  gatilho: string;
  criado_por: string | null;
  criado_em: string;
  expira_em: string | null;
  ativo: boolean;
  desbloqueado_por: string | null;
  desbloqueado_em: string | null;
  notificacao_status: "nao_aplica" | "enviada" | "falhou";
}

export const ROTULO_GATILHO: Record<string, string> = {
  manual: "Manual", entrada_flood: "Excesso de mensagens", limite_taxa: "Limite de taxa do agente", loop_detectado: "Loop detectado",
};

export const PROTECAO_KEY = ["sw", "julia", "protecao"] as const;
const BASE = "/api/julia/protecao";

export function useConfigProtecao(enabled = true) {
  const q = useQuery({
    enabled,
    queryKey: [...PROTECAO_KEY, "config"],
    queryFn: async () => (await api.get<{ data: ConfigProtecao }>(`${BASE}/config`)).data,
  });
  return { ...q, showSkeleton: q.isPending && !q.data, isRefreshing: q.isFetching && !!q.data };
}

export function useSalvarConfigProtecao() {
  const qc = useQueryClient();
  return useMutation<unknown, unknown, ConfigEntrada>({ // noc-allow: invalidate-only — the PUT answer is not the read shape: `padrao`, `faixas`, `atualizado_em` and clamped values are server-computed
    mutationFn: (campos) => api.put(`${BASE}/config`, campos),
    onSettled: () => qc.invalidateQueries({ queryKey: [...PROTECAO_KEY, "config"] }),
  });
}

export function useBloqueios(historico: boolean, enabled = true) {
  const q = useQuery({
    enabled,
    queryKey: [...PROTECAO_KEY, "bloqueios", historico],
    queryFn: async () => (await api.get<{ data: { items: Bloqueio[] } }>(`${BASE}/bloqueios${historico ? "?historico=true" : ""}`)).data.items,
  });
  return { ...q, showSkeleton: q.isPending && !q.data, isRefreshing: q.isFetching && !!q.data };
}

export function useBloquearNumero() {
  const qc = useQueryClient();
  return useMutation<unknown, unknown, { numero: string; motivo: string; duracao_min?: number }>({ // noc-allow: invalidate-only — the answer carries no row: the bloqueio id, expiry, origin and notification status are server-assigned
    mutationFn: (corpo) => api.post(`${BASE}/bloqueios`, corpo),
    onSettled: () => qc.invalidateQueries({ queryKey: [...PROTECAO_KEY, "bloqueios"] }),
  });
}

export function useDesbloquearNumero() {
  return useCacheWriteMutation<unknown, { id: string }>({
    mutationFn: ({ id }) => api.post(`${BASE}/bloqueios/${encodeURIComponent(id)}/desbloquear`, {}),
    targets: ({ id }) => [
      {
        // The active list drops it; the history list keeps it, no longer active.
        queryKey: [...PROTECAO_KEY, "bloqueios", false],
        optimistic: (old: Bloqueio[] | undefined) => listOps.remove(old, id),
      },
      {
        queryKey: [...PROTECAO_KEY, "bloqueios", true],
        optimistic: (old: Bloqueio[] | undefined) => listOps.patch(old, id, { ativo: false }),
      },
    ],
    invalidate: [[...PROTECAO_KEY, "bloqueios"]],
  });
}

export interface Permitido {
  id: string;
  numero: string;
  rotulo: string | null;
  criado_em: string;
}
export interface PermitidosLista {
  ativo: boolean;
  items: Permitido[];
}
export const PERMITIDOS_KEY = [...PROTECAO_KEY, "permitidos"] as const;
const CONFIG_KEY = [...PROTECAO_KEY, "config"] as const;

export function usePermitidos(enabled = true) {
  const q = useQuery({
    enabled,
    queryKey: PERMITIDOS_KEY,
    queryFn: async () => (await api.get<{ data: PermitidosLista }>(`${BASE}/permitidos`)).data,
  });
  return { ...q, showSkeleton: q.isPending && !q.data, isRefreshing: q.isFetching && !!q.data };
}

/** The server assigns the id and the timestamp: the answer (the row) is committed into the list. */
export function useAdicionarPermitido() {
  return useCacheWriteMutation<Permitido, { numero: string; rotulo?: string }>({
    mutationFn: async (corpo) => (await api.post<{ data: Permitido }>(`${BASE}/permitidos`, corpo)).data,
    targets: [
      {
        queryKey: PERMITIDOS_KEY,
        commit: (old: PermitidosLista | undefined, saved) =>
          listOps.within(old, "items", (l) => listOps.replace(l, saved.id, saved)),
      },
    ],
  });
}

export function useRemoverPermitido() {
  return useCacheWriteMutation<unknown, { id: string }>({
    mutationFn: ({ id }) => api.delete(`${BASE}/permitidos/${encodeURIComponent(id)}`),
    targets: ({ id }) => [
      {
        queryKey: PERMITIDOS_KEY,
        optimistic: (old: PermitidosLista | undefined) => listOps.within(old, "items", (l) => listOps.remove(l, id)),
      },
    ],
  });
}

/** The switch: exactly what the user sent goes into BOTH reads that carry it (list envelope + config). */
export function useAlternarPermitidosAtivo() {
  const patch = (v: boolean) => [
    {
      queryKey: PERMITIDOS_KEY,
      optimistic: (old: PermitidosLista | undefined) => (old ? { ...old, ativo: v } : old),
    },
    {
      queryKey: CONFIG_KEY,
      optimistic: (old: ConfigProtecao | undefined) => (old ? { ...old, permitidos_ativo: v } : old),
    },
  ];
  return useCacheWriteMutation<unknown, { ativo: boolean }>({
    mutationFn: ({ ativo }) => api.put(`${BASE}/config`, { permitidos_ativo: ativo }),
    targets: ({ ativo }) => patch(ativo),
  });
}
