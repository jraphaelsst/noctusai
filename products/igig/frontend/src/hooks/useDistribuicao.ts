/**
 * Distribuição e métricas hooks — Módulo 5.
 *
 * Backend mirror: `app/routers/distribuicao_router.py`.
 *
 * `executar` is a mutation with no optimistic update on purpose: a publish
 * either succeeds with a platform id or fails, and optimistically showing
 * "publicada" would be the exact lie this module is built to avoid.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@noctusai/lib";
import { addTo, patchById, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

import { api } from "@/lib/api";
import { INTEGRACOES_QUERY_KEY } from "@/hooks/useIntegracoes";

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

const PUBLICACOES_KEY = [...DISTRIBUICAO_QUERY_KEY, "publicacoes"] as const;
const FILA_KEY = [...DISTRIBUICAO_QUERY_KEY, "fila"] as const;

/** A publication row lives in the per-pauta lists AND the scheduled queue. */
function publicacaoTargets<TVars>(idOf: (v: TVars) => string, changesOf?: (v: TVars) => object) {
  return [
    patchById<Publicacao, TVars>(PUBLICACOES_KEY, idOf, changesOf),
    patchById<Publicacao, TVars>(FILA_KEY, idOf, changesOf),
  ];
}

export function useAgendarPublicacao() {
  type Vars = { pauta_id: string; canal: Canal; agendada_para: string };
  return useCacheWriteMutation<Publicacao, Vars>({
    mutationFn: (payload) => api.post<Publicacao>("/api/distribuicao/publicacoes", payload),
    // The new row belongs in its pauta's list and the all-pautas list; the
    // queue (ordered server-side) and the BI settle in the background.
    targets: (v) => [
      addTo<Publicacao, Vars>([...PUBLICACOES_KEY, v.pauta_id]),
      addTo<Publicacao, Vars>([...PUBLICACOES_KEY, ""]),
    ],
    invalidate: [DISTRIBUICAO_QUERY_KEY],
  });
}

/** Edit / reschedule a still-`agendada` publication (PATCH). */
export function useEditarPublicacao() {
  type Vars = { id: string; canal?: Canal; agendada_para?: string };
  return useCacheWriteMutation<Publicacao, Vars>({
    mutationFn: ({ id, ...payload }) => api.patch<Publicacao>(`/api/distribuicao/publicacoes/${id}`, payload),
    targets: publicacaoTargets<Vars>((v) => v.id, ({ id: _id, ...changes }) => changes),
    invalidate: [DISTRIBUICAO_QUERY_KEY],
  });
}

export function useExecutarPublicacao() {
  const qc = useQueryClient();
  return useCacheWriteMutation<Publicacao, string>({
    mutationFn: (id) => api.post<Publicacao>(`/api/distribuicao/publicacoes/${id}/executar`, {}),
    // No optimism on purpose (see the module docstring): the row shows what the
    // server says — publicada with a platform id, or falhou — as soon as it answers.
    targets: publicacaoTargets<string>((id) => id),
    invalidate: [DISTRIBUICAO_QUERY_KEY],
    onError: (erro) => {
      // `credencial_ilegivel` writes integracao.reconectar_necessario
      // server-side (distribuicao_router.executar_publicacao ->
      // integracao.registrar_erro) — the Integrações page's cached
      // "reconectar" badge must not go stale until a manual refresh.
      if (erro instanceof ApiError && erro.code === "credencial_ilegivel") {
        qc.invalidateQueries({ queryKey: INTEGRACOES_QUERY_KEY });
      }
    },
  });
}

export function useCancelarPublicacao() {
  return useCacheWriteMutation<Publicacao, string>({
    mutationFn: (id) => api.post<Publicacao>(`/api/distribuicao/publicacoes/${id}/cancelar`, {}),
    targets: publicacaoTargets<string>((id) => id, () => ({ status: "cancelada" as const })),
    invalidate: [DISTRIBUICAO_QUERY_KEY],
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
  type Vars = {
    publicacaoId: string;
    curtidas?: number;
    comentarios?: number;
    compartilhamentos?: number;
    alcance?: number;
    cliques_bio?: number;
    visualizacoes?: number;
  };
  return useCacheWriteMutation<Metrica, Vars>({
    mutationFn: ({ publicacaoId, ...payload }) =>
      api.post<Metrica>(`/api/distribuicao/publicacoes/${publicacaoId}/metricas`, payload),
    targets: (v) => [addTo<Metrica, Vars>([...DISTRIBUICAO_QUERY_KEY, "metricas", v.publicacaoId])],
    // The BI de eficiência is derived from the metrics — never recomputed here.
    invalidate: [DISTRIBUICAO_QUERY_KEY],
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
