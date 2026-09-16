/**
 * Membros data hooks — community-m1-contract.md §Endpoints#Membros.
 *
 * The list endpoint's envelope carries `resumo` (org-wide status counts,
 * computed with every filter EXCEPT `status` applied — so tab badges don't
 * change when a tab is selected) alongside `items`/`total`.
 */
import { useMutation, useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";

import { api } from "@/lib/api";

export type MembroStatus = "pendente" | "ativo" | "atrasado" | "pausado" | "cancelado";
export type MembroOrigem = "checkout" | "aplicacao" | "convite";

export interface Membro {
  id: string;
  nome: string;
  email: string;
  telefone: string | null;
  status: MembroStatus;
  plano_id: string | null;
  plano_nome: string | null;
  origem: MembroOrigem;
  tags: string[];
  user_id: string | null;
  observacoes: string | null;
  entrou_em: string | null;
  created_at: string;
  updated_at: string;
}

export interface MembrosResumo {
  pendente: number;
  ativo: number;
  atrasado: number;
  pausado: number;
  cancelado: number;
}

export interface MembroListResponse {
  items: Membro[];
  total: number;
  resumo: MembrosResumo;
}

export interface MembrosParams {
  /** Comma-separated status list, e.g. `"ativo,atrasado"`. */
  status?: string;
  plano_id?: string;
  tag?: string;
  busca?: string;
  page?: number;
  page_size?: number;
}

export interface MembroCreateInput {
  nome: string;
  email: string;
  telefone?: string | null;
  status?: MembroStatus;
  plano_id?: string | null;
  origem: MembroOrigem;
  tags?: string[];
  observacoes?: string | null;
}

export type MembroUpdateInput = Partial<MembroCreateInput>;

export interface MembroStatusChangeInput {
  status: MembroStatus;
  motivo?: string;
}

const membrosKeys = {
  all: ["membros"] as const,
  list: (params?: MembrosParams) => ["membros", "list", params ?? {}] as const,
  detail: (id: string) => ["membros", "detail", id] as const,
};

export function useMembros(params?: MembrosParams) {
  return useQuery({
    queryKey: membrosKeys.list(params),
    queryFn: () => api.get<MembroListResponse>("/api/membros", params),
    placeholderData: keepPreviousData,
  });
}

export function useMembro(id?: string | null) {
  return useQuery({
    queryKey: membrosKeys.detail(id ?? ""),
    queryFn: () => api.get<Membro>(`/api/membros/${id}`),
    enabled: !!id,
  });
}

export function useCreateMembro() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: MembroCreateInput) => api.post<Membro>("/api/membros", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: membrosKeys.all }),
  });
}

export function useUpdateMembro() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: { id: string } & MembroUpdateInput) =>
      api.patch<Membro>(`/api/membros/${id}`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: membrosKeys.all }),
  });
}

/** A status change is an event, not a field edit (own endpoint — module 2's
 * payment-driven transitions hang off the same backend service function). */
export function useChangeMembroStatus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: { id: string } & MembroStatusChangeInput) =>
      api.post<Membro>(`/api/membros/${id}/status`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: membrosKeys.all }),
  });
}

/** Sets `status='cancelado'` (204). Never a hard delete — LGPD erasure is a
 * separate, later flow. */
export function useCancelMembro() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/membros/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: membrosKeys.all }),
  });
}
