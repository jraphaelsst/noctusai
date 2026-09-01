/**
 * Cliente hooks — Módulo 1 (CRM).
 *
 * TanStack Query per the platform convention (`KB § 03-SEED-ARCHITECTURE.md`:
 * one hook file per domain entity; never inline useQuery/useMutation in a
 * page). Backend mirror: `app/routers/cliente_router.py`.
 *
 * `loading` is `isPending && !data` — first load only, never `isLoading`
 * and never `|| isFetching`. TanStack v5's `isLoading` is false during a
 * background refetch, so gating on it (or on a plain `isFetching`) would
 * render "nenhum cliente" — or unmount the list entirely — over data that
 * is merely refetching, e.g. right after `useCriarCliente` invalidates the
 * list while the user is still typing in `busca`. `useClientes` also carries
 * `placeholderData: (prev) => prev` for exactly that case: the previous
 * result set stays on screen (instead of blanking) while the new one is
 * in flight. The lying-loading-state class the `check_lying_loading_state`
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
    // `busca`/`status` ride in the query key, so every keystroke is a new
    // key. Without this the list would blank to the skeleton on each
    // keystroke while the previous key's data is thrown away; with it, the
    // prior result set stays on screen until the new one lands.
    placeholderData: (prev) => prev,
  });

  return {
    ...query,
    clientes: query.data?.itens ?? [],
    total: query.data?.total ?? 0,
    // See the module docstring: isPending && !data, never isLoading and
    // never `|| isFetching`.
    loading: query.isPending && !query.data,
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

/**
 * Edit a client.
 *
 * `PATCH /api/clientes/{id}` shipped with the router but had no consumer, so
 * the U of CRUD was simply absent: `email`, `telefone`, `origem`,
 * `observacoes` and any status change other than prospect→ativo could be
 * written by the API and never by a human. A CRM whose contact fields cannot
 * be corrected is not a CRM.
 */
export function useAtualizarCliente() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...patch }: Partial<ClienteCreate> & { id: string; status?: StatusCliente }) =>
      api.patch<Cliente>(`/api/clientes/${id}`, patch),
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
