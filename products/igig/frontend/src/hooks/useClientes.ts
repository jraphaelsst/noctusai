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
import { useQuery } from "@tanstack/react-query";
import { addTo, patchById, removeById, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

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

/** PATCH payload — `null` CLEARS a field (the backend uses `exclude_unset`,
 * never `exclude_none`, precisely so a `null` is distinguishable from
 * "not sent"). */
export type ClienteUpdate = {
  nome?: string;
  nicho?: string | null;
  email?: string | null;
  telefone?: string | null;
  origem?: string | null;
  observacoes?: string | null;
  status?: StatusCliente;
};

export interface ClientesFiltros {
  busca?: string;
  status?: StatusCliente;
  /** Page size — server default/cap is 50 (`limit` query param, 1..200). */
  limit?: number;
  offset?: number;
}

export const CLIENTES_QUERY_KEY = ["igig", "clientes"] as const;

/** Only send params that are set — an empty `busca=` would filter on "". */
function buildParams(filtros: ClientesFiltros): Record<string, string> {
  const params: Record<string, string> = {};
  if (filtros.busca) params.busca = filtros.busca;
  if (filtros.status) params.status = filtros.status;
  if (filtros.limit != null) params.limit = String(filtros.limit);
  if (filtros.offset) params.offset = String(filtros.offset);
  return params;
}

/**
 * List clients for the caller's org, optionally filtered + paged.
 *
 * The list used to silently cap at the server's default `limit=50` with no
 * paging control at all (achado plat#6 / #7): the header's own `total`
 * proved more clientes existed than the page ever showed, with no way to
 * reach them besides `busca`.
 */
export function useClientes(filtros: ClientesFiltros = {}) {
  const query = useQuery({
    queryKey: [
      ...CLIENTES_QUERY_KEY, filtros.busca ?? "", filtros.status ?? "",
      filtros.limit ?? "", filtros.offset ?? "",
    ],
    queryFn: () => api.get<ClienteListResponse>("/api/clientes", buildParams(filtros)),
    // `busca`/`status`/paging ride in the query key, so every keystroke or
    // page change is a new key. Without this the list would blank to the
    // skeleton on each change while the previous key's data is thrown away;
    // with it, the prior result set stays on screen until the new one lands.
    placeholderData: (prev) => prev,
  });

  return {
    ...query,
    clientes: query.data?.itens ?? [],
    total: query.data?.total ?? 0,
    // See the module docstring: isPending && !data, never isLoading and
    // never `|| isFetching`.
    loading: query.isPending && !query.data,
    /** Indicator only (never gates what renders): a refetch over data. */
    isRefreshing: query.isFetching && !!query.data,
  };
}

/**
 * One cliente by id — what the card needs when it is opened by deep link
 * (`/clientes?id=…`) before (or without) the list containing it: a filtered
 * list, a second page, or a cliente the list has not refetched yet.
 */
export function useCliente(id: string | null) {
  const query = useQuery({
    queryKey: [...CLIENTES_QUERY_KEY, "detalhe", id ?? "__none__"],
    queryFn: () => api.get<Cliente>(`/api/clientes/${encodeURIComponent(id as string)}`),
    enabled: !!id,
  });
  return {
    ...query,
    cliente: query.data ?? null,
    showSkeleton: !!id && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

/**
 * The list a brand-new cliente certainly belongs in: no busca, no status
 * filter, first page (`useClientes()` with no arguments). Filtered lists
 * converge on the background settle.
 */
const LISTA_SEM_FILTRO = [...CLIENTES_QUERY_KEY, "", "", "", ""] as const;

/**
 * Create a cliente. The server decides the row (id, status), so it is
 * committed into the default list the moment the POST answers — no waiting
 * for the list to be fetched again.
 */
export function useCriarCliente() {
  return useCacheWriteMutation<Cliente, ClienteCreate>({
    mutationFn: (payload) => api.post<Cliente>("/api/clientes", payload),
    targets: [addTo<Cliente, ClienteCreate>(LISTA_SEM_FILTRO, "prepend")],
    invalidate: [CLIENTES_QUERY_KEY],
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
  return useCacheWriteMutation<Cliente, string>({
    mutationFn: (id) => api.post<Cliente>(`/api/clientes/${id}/ativar`, {}),
    targets: [patchById<Cliente, string>(CLIENTES_QUERY_KEY, (id) => id, () => ({ status: "ativo" }))],
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
  return useCacheWriteMutation<Cliente, ClienteUpdate & { id: string }>({
    mutationFn: ({ id, ...patch }) => api.patch<Cliente>(`/api/clientes/${id}`, patch),
    targets: [patchById<Cliente, ClienteUpdate & { id: string }>(CLIENTES_QUERY_KEY, (v) => v.id, ({ id: _id, ...changes }) => changes)],
  });
}

export function useRemoverCliente() {
  return useCacheWriteMutation<{ ok: boolean }, string>({
    mutationFn: (id) => api.delete<{ ok: boolean }>(`/api/clientes/${id}`),
    targets: [removeById<{ ok: boolean }, string>(CLIENTES_QUERY_KEY, (id) => id)],
  });
}
