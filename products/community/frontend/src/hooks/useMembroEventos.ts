/**
 * Member relationship timeline + login provisioning — CONTRACT.md
 * (ninho-vazio) §Identity, `/api/membros/{id}/eventos` and
 * `/api/membros/{id}/acesso`.
 *
 * `useCriarAcesso` returns a one-time temporary password. It is handed to
 * the caller through the mutation result only — never written to the query
 * cache, storage or logs — and the dialog that shows it drops it on close.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

export type EventoTipo =
  | "status"
  | "plano"
  | "pagamento"
  | "assinatura"
  | "nota"
  | "contato"
  | "acesso"
  | "grupoterapia"
  | "sistema";

export interface Evento {
  id: string;
  tipo: EventoTipo;
  descricao: string;
  dados: Record<string, unknown> | null;
  autor_id: string | null;
  autor_nome: string | null;
  created_at: string;
}

export interface EventoListResponse {
  items: Evento[];
  total: number;
}

export interface EventoCreateInput {
  tipo: "nota" | "contato";
  descricao: string;
}

export interface CriarAcessoResponse {
  email: string;
  senha_temporaria: string;
}

const eventosKeys = {
  all: (membroId: string) => ["membros", "eventos", membroId] as const,
  list: (membroId: string, page: number, pageSize: number) =>
    ["membros", "eventos", membroId, page, pageSize] as const,
};

export function useMembroEventos(membroId?: string | null, page = 1, pageSize = 50) {
  return useQuery({
    queryKey: eventosKeys.list(membroId ?? "", page, pageSize),
    queryFn: () =>
      api.get<EventoListResponse>(`/api/membros/${membroId}/eventos`, { page, page_size: pageSize }),
    enabled: !!membroId,
    placeholderData: keepPreviousData,
  });
}

export function useCreateMembroEvento(membroId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: EventoCreateInput) => api.post<Evento>(`/api/membros/${membroId}/eventos`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: eventosKeys.all(membroId) }),
  });
}

export function useCriarAcesso() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (membroId: string) => api.post<CriarAcessoResponse>(`/api/membros/${membroId}/acesso`, {}),
    // The result carries the one-time password: drop it from the mutation
    // cache the moment the dialog stops observing it.
    gcTime: 0,
    // Refresh the member (user_id now set) and its timeline (evento `acesso`).
    // The 409 "already linked" path also changes both, so settle, not success.
    onSettled: () => qc.invalidateQueries({ queryKey: ["membros"] }),
  });
}
