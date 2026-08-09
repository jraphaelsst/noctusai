/**
 * Cliente hooks — Módulo 1 (CRM).
 *
 * TanStack Query per the platform convention (`KB § 03-SEED-ARCHITECTURE.md`:
 * one hook file per domain entity; never inline useQuery/useMutation in a
 * page). Backend mirror: `app/routers/cliente_router.py`.
 *
 * Loading is exposed as `isPending || isFetching`, never `isLoading`. In
 * TanStack v5 `isLoading` is false during a background refetch, so a page
 * gating an empty-state on it renders "nenhum cliente" over data that
 * exists — the lying-loading-state class the `check_lying_loading_state`
 * keeper blocks.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

// ─── Types (mirror backend app/schemas/cliente.py) ─────────────────────
export type StatusCliente = "prospect" | "ativo" | "inativo" | "inadimplente";

export interface Cliente {
  id: string;
  org_id: string;
  nome: string;
  nicho: string | null;
  email: string | null;
  telefone: string | null;
  status: StatusCliente;
  origem: string | null;
  observacoes: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface ClienteListResponse {
  itens: Cliente[];
  /** Total matching the filters — NOT the page size. Drives pagination. */
  total: number;
}

export interface ClienteCreate {
  nome: string;
  nicho?: string;
  email?: string;
  telefone?: string;
  origem?: string;
  observacoes?: string;
}

export interface ClientesFiltros {
  busca?: string;
  status?: StatusCliente;
}

export const CLIENTES_QUERY_KEY = ["igig", "clientes"] as const;

/** Only send params that are set — an empty `busca=` would filter on "". */
function buildParams(filtros: ClientesFiltros): Record<string, string> {
  const params: Record<string, string> = {};
  if (filtros.busca) params.busca = filtros.busca;
  if (filtros.status) params.status = filtros.status;
  return params;
}

/** List clients for the caller's org, optionally filtered. */
export function useClientes(filtros: ClientesFiltros = {}) {
  const query = useQuery({
    queryKey: [...CLIENTES_QUERY_KEY, filtros.busca ?? "", filtros.status ?? ""],
    queryFn: () => api.get<ClienteListResponse>("/api/clientes", buildParams(filtros)),
  });

  return {
    ...query,
    clientes: query.data?.itens ?? [],
    total: query.data?.total ?? 0,
    // See the module docstring: isPending || isFetching, never isLoading.
    loading: query.isPending || query.isFetching,
  };
}

export function useCriarCliente() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ClienteCreate) => api.post<Cliente>("/api/clientes", payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: CLIENTES_QUERY_KEY }),
  });
}

/**
 * Promote a prospect to ativo.
 *
 * A dedicated endpoint rather than a PATCH: Módulo 1's signature webhook
 * performs exactly this transition, and a generic status write would lose
 * that intent.
 */
export function useAtivarCliente() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<Cliente>(`/api/clientes/${id}/ativar`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: CLIENTES_QUERY_KEY }),
  });
}

export function useRemoverCliente() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<{ ok: boolean }>(`/api/clientes/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: CLIENTES_QUERY_KEY }),
  });
}
