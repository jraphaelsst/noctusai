/**
 * Julia › Equipes (contract wave 11).
 *
 *   GET/POST /api/julia/equipes · PATCH/DELETE /api/julia/equipes/{id}
 *   POST /api/julia/equipes/{id}/membros {user_id} · DELETE …/membros/{user_id}
 *   PUT  /api/julia/equipes/{id}/membros/ordem {ordem: [user_id…]} (exactly the current members)
 *   GET  /api/julia/equipes/{id}/metricas?mes=YYYY-MM → {membros:[{…, tpr_medio_s, tpr_amostras, distribuicao_pct}], total_atribuicoes, fontes}
 *
 * Loading = two signals off `data` (never `isLoading`); reads are member-open,
 * writes admin-only (server enforces).
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

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

export const EQUIPES_KEY = ["sw", "julia", "equipes"] as const;

export function useJuliaEquipes() {
  const q = useQuery({
    queryKey: EQUIPES_KEY,
    placeholderData: keepPreviousData,
    queryFn: async () => (await api.get<{ data: Equipe[] }>("/api/julia/equipes")).data ?? [],
  });
  return { ...q, showSkeleton: q.isPending && !q.data, isRefreshing: q.isFetching && !!q.data };
}

/** The team list (exact key — the metrics queries share the prefix and are not edited here). */
const emEquipe = (id: string, fn: (e: Equipe) => Equipe) => (old: Equipe[] | undefined) =>
  Array.isArray(old) ? old.map((e) => (e.id === id ? fn(e) : e)) : old;

/** Create a team and (optionally) add its members in order. */
export function useCriarEquipe() {
  return useCacheWriteMutation<Equipe, EquipeInput & { user_ids: string[] }>({
    mutationFn: async ({ user_ids, ...body }) => {
      const eq = (await api.post<{ data: Equipe }>("/api/julia/equipes", body)).data;
      for (const user_id of user_ids) {
        await api.post(`/api/julia/equipes/${eq.id}/membros`, { user_id });
      }
      return eq;
    },
    // The members were added after the team was created: the settle brings their names/order.
    targets: [{ queryKey: EQUIPES_KEY, commit: (old: Equipe[] | undefined, saved) => listOps.replace(old, saved.id, saved) }],
  });
}

export function useAtualizarEquipe() {
  return useCacheWriteMutation<unknown, { id: string } & Partial<EquipeInput>>({
    mutationFn: ({ id, ...body }) => api.patch(`/api/julia/equipes/${id}`, body),
    targets: ({ id, ...changes }) => [
      { queryKey: EQUIPES_KEY, optimistic: (old: Equipe[] | undefined) => listOps.patch(old, id, changes) },
    ],
  });
}

export function useExcluirEquipe() {
  return useCacheWriteMutation<unknown, string>({
    mutationFn: (id) => api.delete(`/api/julia/equipes/${id}`),
    targets: (id) => [{ queryKey: EQUIPES_KEY, optimistic: (old: Equipe[] | undefined) => listOps.remove(old, id) }],
  });
}

export function useAdicionarMembro() {
  const qc = useQueryClient();
  return useMutation<unknown, unknown, { id: string; user_id: string }>({ // noc-allow: invalidate-only — the new member row needs the user's name and the server-assigned order, and the response carries neither
    mutationFn: ({ id, user_id }) => api.post(`/api/julia/equipes/${id}/membros`, { user_id }),
    onSettled: () => qc.invalidateQueries({ queryKey: EQUIPES_KEY }),
  });
}

export function useRemoverMembro() {
  return useCacheWriteMutation<unknown, { id: string; user_id: string }>({
    mutationFn: ({ id, user_id }) => api.delete(`/api/julia/equipes/${id}/membros/${user_id}`),
    targets: ({ id, user_id }) => [
      {
        queryKey: EQUIPES_KEY,
        optimistic: emEquipe(id, (e) => ({ ...e, membros: e.membros.filter((m) => m.user_id !== user_id) })),
      },
    ],
  });
}

export function useOrdenarMembros() {
  return useCacheWriteMutation<unknown, { id: string; user_ids: string[] }>({
    mutationFn: ({ id, user_ids }) => api.put(`/api/julia/equipes/${id}/membros/ordem`, { ordem: user_ids }),
    // The order is exactly the one sent (the server requires the current members).
    targets: ({ id, user_ids }) => [
      {
        queryKey: EQUIPES_KEY,
        optimistic: emEquipe(id, (e) => ({
          ...e,
          membros: user_ids
            .map((uid, ordem) => {
              const m = e.membros.find((x) => x.user_id === uid);
              return m ? { ...m, ordem } : null;
            })
            .filter((m): m is EquipeMembro => m !== null),
        })),
      },
    ],
  });
}

export function useMetricasEquipe(id: string | null, mes: string) {
  const q = useQuery({
    queryKey: [...EQUIPES_KEY, id, "metricas", mes] as const,
    enabled: !!id,
    placeholderData: keepPreviousData,
    queryFn: async (): Promise<MetricaMembro[]> => {
      const d = (await api.get<{ data: { membros: MetricaApi[] } }>(`/api/julia/equipes/${id}/metricas?mes=${mes}`)).data;
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
