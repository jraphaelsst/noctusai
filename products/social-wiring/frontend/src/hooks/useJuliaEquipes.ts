/**
 * Lais › Equipes (contract wave 11).
 *
 *   GET/POST /api/lais/equipes · PATCH/DELETE /api/lais/equipes/{id}
 *   POST /api/lais/equipes/{id}/membros {user_id} · DELETE …/membros/{user_id}
 *   PUT  /api/lais/equipes/{id}/membros/ordem {ordem: [user_id…]} (exactly the current members)
 *   GET  /api/lais/equipes/{id}/metricas?mes=YYYY-MM → {membros:[{…, tpr_medio_s, tpr_amostras, distribuicao_pct}], total_atribuicoes, fontes}
 *
 * Loading = two signals off `data` (never `isLoading`); reads are member-open,
 * writes admin-only (server enforces).
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

export type ModoDistribuicao = "funil" | "julia";

export interface EquipeMembro { user_id: string; nome: string; ativo: boolean; ordem: number }
export interface Equipe {
  id: string;
  nome: string;
  atende_apos_julia: boolean;
  modo: ModoDistribuicao;
  manter_ultimo: boolean;
  membros: EquipeMembro[];
}
export interface EquipeInput {
  nome: string;
  atende_apos_julia: boolean;
  modo: ModoDistribuicao;
  manter_ultimo: boolean;
}
export interface MetricaMembro {
  user_id: string;
  nome: string;
  ultimo_acesso: string | null;
  tpr_segundos: number | null;
  conversas: number;
  distribuicao: number;
}

interface MetricaApi {
  user_id: string; nome: string; ultimo_acesso: string | null; tpr_medio_s: number | null;
  tpr_amostras: number; conversas: number; distribuicao: number; distribuicao_pct: number;
}

export const EQUIPES_KEY = ["sw", "lais", "equipes"] as const;

export function useLaisEquipes() {
  const q = useQuery({
    queryKey: EQUIPES_KEY,
    placeholderData: keepPreviousData,
    queryFn: async () => (await api.get<{ data: Equipe[] }>("/api/lais/equipes")).data ?? [],
  });
  return { ...q, showSkeleton: q.isPending && !q.data, isRefreshing: q.isFetching && !!q.data };
}

function useInvalidar() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: EQUIPES_KEY });
}

/** Create a team and (optionally) add its members in order. */
export function useCriarEquipe() {
  const inv = useInvalidar();
  return useMutation<Equipe, unknown, EquipeInput & { user_ids: string[] }>({
    mutationFn: async ({ user_ids, ...body }) => {
      const eq = (await api.post<{ data: Equipe }>("/api/lais/equipes", body)).data;
      for (const user_id of user_ids) {
        await api.post(`/api/lais/equipes/${eq.id}/membros`, { user_id });
      }
      return eq;
    },
    onSettled: inv,
  });
}

export function useAtualizarEquipe() {
  const inv = useInvalidar();
  return useMutation<unknown, unknown, { id: string } & Partial<EquipeInput>>({
    mutationFn: ({ id, ...body }) => api.patch(`/api/lais/equipes/${id}`, body),
    onSettled: inv,
  });
}

export function useExcluirEquipe() {
  const inv = useInvalidar();
  return useMutation<unknown, unknown, string>({
    mutationFn: (id) => api.delete(`/api/lais/equipes/${id}`),
    onSettled: inv,
  });
}

export function useAdicionarMembro() {
  const inv = useInvalidar();
  return useMutation<unknown, unknown, { id: string; user_id: string }>({
    mutationFn: ({ id, user_id }) => api.post(`/api/lais/equipes/${id}/membros`, { user_id }),
    onSettled: inv,
  });
}

export function useRemoverMembro() {
  const inv = useInvalidar();
  return useMutation<unknown, unknown, { id: string; user_id: string }>({
    mutationFn: ({ id, user_id }) => api.delete(`/api/lais/equipes/${id}/membros/${user_id}`),
    onSettled: inv,
  });
}

export function useOrdenarMembros() {
  const inv = useInvalidar();
  return useMutation<unknown, unknown, { id: string; user_ids: string[] }>({
    mutationFn: ({ id, user_ids }) => api.put(`/api/lais/equipes/${id}/membros/ordem`, { ordem: user_ids }),
    onSettled: inv,
  });
}

export function useMetricasEquipe(id: string | null, mes: string) {
  const q = useQuery({
    queryKey: [...EQUIPES_KEY, id, "metricas", mes] as const,
    enabled: !!id,
    placeholderData: keepPreviousData,
    queryFn: async (): Promise<MetricaMembro[]> => {
      const d = (await api.get<{ data: { membros: MetricaApi[] } }>(`/api/lais/equipes/${id}/metricas?mes=${mes}`)).data;
      return (d?.membros ?? []).map((m) => ({
        user_id: m.user_id, nome: m.nome, ultimo_acesso: m.ultimo_acesso,
        tpr_segundos: m.tpr_medio_s, conversas: m.conversas, distribuicao: m.distribuicao,
      }));
    },
  });
  return { ...q, showSkeleton: q.isPending && !q.data, isRefreshing: q.isFetching && !!q.data };
}

/** "YYYY-MM" for a date (local). */
export function mesAtual(d = new Date()): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function formatarTpr(seg: number | null | undefined): string {
  if (seg == null) return "—";
  if (seg < 60) return `${Math.round(seg)}s`;
  if (seg < 3600) return `${Math.round(seg / 60)} min`;
  const h = Math.floor(seg / 3600);
  const m = Math.round((seg % 3600) / 60);
  return m ? `${h}h ${m}min` : `${h}h`;
}
