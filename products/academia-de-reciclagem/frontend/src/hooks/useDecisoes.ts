/**
 * Decisions data hooks — contract §A.2, §B.2.
 *
 * Append-only entity: no update/delete hooks exist (the contract has no
 * PUT/DELETE for decisions — only create and supersede).
 */
import { useMutation, useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { Envelope } from "@/lib/types";

export type DecisaoEstado = "vigente" | "superseded";

export interface Decision {
  codigo: string;
  titulo: string;
  contexto: string | null;
  decisao: string;
  motivo: string;
  alternativas_rejeitadas: string | null;
  data: string;
  estado: DecisaoEstado;
  substitui: string | null;
  superseded_by: string | null;
  relacionadas: string[];
}

const decisoesKeys = {
  all: ["decisoes"] as const,
  list: (estado?: string) => ["decisoes", "list", estado ?? "todas"] as const,
  detail: (codigo: string) => ["decisoes", "detail", codigo] as const,
};

export function useDecisoesList(estado?: DecisaoEstado) {
  return useQuery({
    queryKey: decisoesKeys.list(estado),
    queryFn: () =>
      api.get<Envelope<Decision>>("/api/decisions", estado ? { estado } : undefined),
    placeholderData: keepPreviousData,
  });
}

export function useDecisao(codigo: string | undefined) {
  return useQuery({
    queryKey: decisoesKeys.detail(codigo ?? ""),
    queryFn: () => api.get<Decision>(`/api/decisions/${codigo}`),
    enabled: !!codigo,
  });
}

export interface DecisaoCreateInput {
  titulo: string;
  contexto?: string;
  decisao: string;
  motivo: string;
  alternativas_rejeitadas?: string;
  relacionadas?: string[];
}

export function useCreateDecisao() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: DecisaoCreateInput) => api.post<Decision>("/api/decisions", data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: decisoesKeys.all });
    },
  });
}

export interface SupersedeResult {
  nova: Decision;
  substituida: Decision;
}

export function useSupersedeDecisao(codigo: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: DecisaoCreateInput) =>
      api.post<SupersedeResult>(`/api/decisions/${codigo}/supersede`, data),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: decisoesKeys.all });
      if (codigo) qc.invalidateQueries({ queryKey: decisoesKeys.detail(codigo) });
      qc.invalidateQueries({ queryKey: decisoesKeys.detail(result.nova.codigo) });
    },
  });
}
