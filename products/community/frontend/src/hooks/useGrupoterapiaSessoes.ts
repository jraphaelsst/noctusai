/**
 * Grupoterapia (staff) hooks — CONTRACT.md (ninho-vazio) §Grupoterapia,
 * `/api/grupoterapia/sessoes*`.
 *
 * A session with reservations is never deleted (409) — it is cancelled,
 * which also writes a timeline evento for every confirmed seat.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { dashboardKeys } from "@/hooks/useDashboard";

export type SessaoStatus = "agendada" | "realizada" | "cancelada";

export interface Sessao {
  id: string;
  titulo: string;
  descricao: string | null;
  /** ISO-8601 UTC */
  inicio: string;
  duracao_minutos: number;
  link_sala: string | null;
  vagas_fala: number;
  status: SessaoStatus;
  reservas: number;
  created_at: string;
  updated_at: string;
}

export interface SessaoListResponse {
  items: Sessao[];
  total: number;
}

export interface SessoesParams {
  de?: string;
  ate?: string;
  status?: SessaoStatus;
}

export interface SessaoInput {
  titulo: string;
  descricao?: string | null;
  inicio: string;
  duracao_minutos?: number;
  link_sala?: string | null;
  vagas_fala?: number;
}

export interface SessaoUpdateInput extends Partial<SessaoInput> {
  status?: SessaoStatus;
}

export interface Reserva {
  id: string;
  membro_id: string;
  membro_nome: string;
  status: "confirmada" | "cancelada";
  created_at: string;
}

export interface ReservaListResponse {
  items: Reserva[];
  total: number;
}

const sessoesKeys = {
  all: ["grupoterapia", "sessoes"] as const,
  list: (params?: SessoesParams) => ["grupoterapia", "sessoes", "list", params ?? {}] as const,
  reservas: (id: string) => ["grupoterapia", "sessoes", "reservas", id] as const,
};

export function useGrupoterapiaSessoes(params?: SessoesParams) {
  return useQuery({
    queryKey: sessoesKeys.list(params),
    queryFn: () => api.get<SessaoListResponse>("/api/grupoterapia/sessoes", params),
    placeholderData: keepPreviousData,
  });
}

export function useSessaoReservas(sessaoId?: string | null) {
  return useQuery({
    queryKey: sessoesKeys.reservas(sessaoId ?? ""),
    queryFn: () => api.get<ReservaListResponse>(`/api/grupoterapia/sessoes/${sessaoId}/reservas`),
    enabled: !!sessaoId,
  });
}

function useInvalidateSessoes() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: sessoesKeys.all });
    qc.invalidateQueries({ queryKey: dashboardKeys.all });
  };
}

export function useCreateSessao() {
  const invalidate = useInvalidateSessoes();
  return useMutation({
    mutationFn: (data: SessaoInput) => api.post<Sessao>("/api/grupoterapia/sessoes", data),
    onSuccess: invalidate,
  });
}

export function useUpdateSessao() {
  const invalidate = useInvalidateSessoes();
  return useMutation({
    mutationFn: ({ id, ...data }: { id: string } & SessaoUpdateInput) =>
      api.patch<Sessao>(`/api/grupoterapia/sessoes/${id}`, data),
    onSuccess: invalidate,
  });
}

export function useDeleteSessao() {
  const invalidate = useInvalidateSessoes();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/grupoterapia/sessoes/${id}`),
    onSuccess: invalidate,
  });
}
