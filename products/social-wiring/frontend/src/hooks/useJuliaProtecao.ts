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
 * Loading = two signals off `data` (never `isLoading`).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

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
export type ConfigEntrada = Partial<Omit<ConfigProtecao, "padrao" | "faixas" | "padroes" | "prompt_documento_padrao">>;

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
  return useMutation<unknown, unknown, ConfigEntrada>({
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

function useInvalidarBloqueios() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: [...PROTECAO_KEY, "bloqueios"] });
}

export function useBloquearNumero() {
  const inv = useInvalidarBloqueios();
  return useMutation<unknown, unknown, { numero: string; motivo: string; duracao_min?: number }>({
    mutationFn: (corpo) => api.post(`${BASE}/bloqueios`, corpo),
    onSettled: inv,
  });
}

export function useDesbloquearNumero() {
  const inv = useInvalidarBloqueios();
  return useMutation<unknown, unknown, { id: string }>({
    mutationFn: ({ id }) => api.post(`${BASE}/bloqueios/${encodeURIComponent(id)}/desbloquear`, {}),
    onSettled: inv,
  });
}
