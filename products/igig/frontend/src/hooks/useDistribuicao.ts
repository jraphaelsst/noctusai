/**
 * Distribuição e métricas hooks — Módulo 5.
 *
 * Backend mirror: `app/routers/distribuicao_router.py`.
 *
 * `executar` is a mutation with no optimistic update on purpose: a publish
 * either succeeds with a platform id or fails, and optimistically showing
 * "publicada" would be the exact lie this module is built to avoid.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

export type Canal = "instagram" | "facebook" | "tiktok" | "linkedin";
export const CANAIS: Canal[] = ["instagram", "facebook", "tiktok", "linkedin"];

export type StatusPublicacao =
  | "agendada" | "publicando" | "publicada" | "falhou" | "cancelada";

export interface Publicacao {
  id: string;
  pauta_id: string;
  canal: Canal;
  status: StatusPublicacao;
  agendada_para: string | null;
  publicada_em: string | null;
  external_id: string | null;
  permalink: string | null;
  erro: string | null;
  tentativas: number;
}

export interface Metrica {
  id: string;
  publicacao_id: string;
  coletada_em: string;
  curtidas: number;
  comentarios: number;
  compartilhamentos: number;
  alcance: number;
  cliques_bio: number;
  visualizacoes: number;
}

export interface Eficiencia {
  cliente_id: string;
  cliente_nome: string;
  tarefas: number;
  refacoes: number;
  taxa_refacao: number;
  horas: number;
  custo_reais: number;
  /** Non-empty ⇒ the cost is UNDERSTATED. Must be surfaced, never hidden. */
  alertas: string[];
}

export const DISTRIBUICAO_QUERY_KEY = ["igig", "distribuicao"] as const;

export function usePublicacoes(pautaId?: string) {
  const query = useQuery({
    queryKey: [...DISTRIBUICAO_QUERY_KEY, "publicacoes", pautaId ?? ""],
    queryFn: () =>
      api.get<Publicacao[]>(
        "/api/distribuicao/publicacoes",
        pautaId ? { pauta_id: pautaId } : {},
      ),
  });
  return {
    ...query,
    publicacoes: query.data ?? [],
    loading: query.isPending && !query.data,
  };
}

export function useAgendarPublicacao() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { pauta_id: string; canal: Canal; agendada_para: string }) =>
      api.post<Publicacao>("/api/distribuicao/publicacoes", payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: DISTRIBUICAO_QUERY_KEY }),
  });
}

export function useExecutarPublicacao() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api.post<Publicacao>(`/api/distribuicao/publicacoes/${id}/executar`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: DISTRIBUICAO_QUERY_KEY }),
  });
}

export function useCancelarPublicacao() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api.post<Publicacao>(`/api/distribuicao/publicacoes/${id}/cancelar`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: DISTRIBUICAO_QUERY_KEY }),
  });
}

/**
 * Record an engagement snapshot by hand.
 *
 * The spec wants these pulled from the platform APIs (Meta/TikTok/LinkedIn),
 * which is blocked on tokens — `NOC-REMEDIATE[igig-publishing]`. Until then
 * the endpoint existed with no consumer, so the BI de eficiência had no way to
 * get numbers at all. Manual entry is explicitly a stopgap, and the UI says so
 * rather than implying the figures arrived automatically. Appends, never
 * overwrites: metrics move over a post's first week.
 */
export function useRegistrarMetrica() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ publicacaoId, ...payload }: {
      publicacaoId: string;
      curtidas?: number;
      comentarios?: number;
      compartilhamentos?: number;
      alcance?: number;
      cliques_bio?: number;
      visualizacoes?: number;
    }) => api.post<Metrica>(`/api/distribuicao/publicacoes/${publicacaoId}/metricas`, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: DISTRIBUICAO_QUERY_KEY }),
  });
}

/** The scheduled-publication queue (`GET /distribuicao/fila`). */
export function useFila() {
  const query = useQuery({
    queryKey: [...DISTRIBUICAO_QUERY_KEY, "fila"],
    queryFn: () => api.get<Publicacao[]>("/api/distribuicao/fila"),
  });
  return { ...query, fila: query.data ?? [], loading: query.isPending && !query.data };
}

export function useMetricas(publicacaoId: string | undefined) {
  const query = useQuery({
    queryKey: [...DISTRIBUICAO_QUERY_KEY, "metricas", publicacaoId],
    queryFn: () => api.get<Metrica[]>(`/api/distribuicao/publicacoes/${publicacaoId}/metricas`),
    enabled: Boolean(publicacaoId),
  });
  // Two signals, never `isLoading` — an empty state gated on `isLoading`
  // renders over data that is merely refetching after a new collection is
  // appended. → KB § PATTERNS/frontend/lying-loading-state.md
  return {
    ...query,
    metricas: query.data ?? [],
    loading: query.isPending && !query.data,
  };
}

export function useEficiencia() {
  const query = useQuery({
    queryKey: [...DISTRIBUICAO_QUERY_KEY, "bi"],
    queryFn: () => api.get<Eficiencia[]>("/api/distribuicao/bi/eficiencia"),
  });
  return {
    ...query,
    linhas: query.data ?? [],
    loading: query.isPending && !query.data,
  };
}
