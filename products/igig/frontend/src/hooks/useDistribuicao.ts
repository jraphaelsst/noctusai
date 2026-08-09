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
    loading: query.isPending || query.isFetching,
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

export function useMetricas(publicacaoId: string | undefined) {
  const query = useQuery({
    queryKey: [...DISTRIBUICAO_QUERY_KEY, "metricas", publicacaoId],
    queryFn: () => api.get<Metrica[]>(`/api/distribuicao/publicacoes/${publicacaoId}/metricas`),
    enabled: Boolean(publicacaoId),
  });
  return { ...query, metricas: query.data ?? [] };
}

export function useEficiencia() {
  const query = useQuery({
    queryKey: [...DISTRIBUICAO_QUERY_KEY, "bi"],
    queryFn: () => api.get<Eficiencia[]>("/api/distribuicao/bi/eficiencia"),
  });
  return {
    ...query,
    linhas: query.data ?? [],
    loading: query.isPending || query.isFetching,
  };
}
