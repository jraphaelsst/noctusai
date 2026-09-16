/**
 * Planos data hooks — community-m1-contract.md §Endpoints#Planos.
 *
 * TanStack Query hooks per the house convention (mirrors
 * `products/academia-de-reciclagem/frontend/src/hooks/usePerguntas.ts`).
 * The list endpoint returns the BARE envelope `{items, total}` (no
 * `resumo` for planos — that's a Membros/Aplicações-only field).
 */
import { useMutation, useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";

import { api } from "@/lib/api";

export type Ciclo = "mensal" | "anual";

export interface Entitlements {
  feed: boolean;
  forum: boolean;
  chat: boolean;
  eventos: boolean;
  conteudo_ids: string[];
  grupos_whatsapp: string[];
  conteudo_todos: boolean;
}

export interface Plano {
  id: string;
  nome: string;
  descricao: string | null;
  preco_centavos: number;
  ciclo: Ciclo;
  entitlements: Entitlements;
  ativo: boolean;
  ordem: number;
  membros_ativos: number;
  created_at: string;
  updated_at: string;
}

export interface PlanoListResponse {
  items: Plano[];
  total: number;
}

export interface PlanosParams {
  ativo?: boolean;
  page?: number;
  page_size?: number;
}

export interface PlanoCreateInput {
  nome: string;
  descricao?: string | null;
  preco_centavos: number;
  ciclo: Ciclo;
  entitlements?: Partial<Entitlements>;
  ordem?: number;
  ativo?: boolean;
}

export type PlanoUpdateInput = Partial<PlanoCreateInput>;

const planosKeys = {
  all: ["planos"] as const,
  list: (params?: PlanosParams) => ["planos", "list", params ?? {}] as const,
  detail: (id: string) => ["planos", "detail", id] as const,
};

export function usePlanos(params?: PlanosParams) {
  return useQuery({
    queryKey: planosKeys.list(params),
    queryFn: () => api.get<PlanoListResponse>("/api/planos", params),
    placeholderData: keepPreviousData,
  });
}

export function usePlano(id?: string | null) {
  return useQuery({
    queryKey: planosKeys.detail(id ?? ""),
    queryFn: () => api.get<Plano>(`/api/planos/${id}`),
    enabled: !!id,
  });
}

export function useCreatePlano() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: PlanoCreateInput) => api.post<Plano>("/api/planos", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: planosKeys.all }),
  });
}

export function useUpdatePlano() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: { id: string } & PlanoUpdateInput) =>
      api.patch<Plano>(`/api/planos/${id}`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: planosKeys.all }),
  });
}

/** Soft-delete (`ativo=false`, 204) — historical member references stay intact. */
export function useDeletePlano() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/planos/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: planosKeys.all }),
  });
}
