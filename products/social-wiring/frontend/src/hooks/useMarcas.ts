/**
 * Clients hooks — TanStack Query wrappers for the client entity CRUD.
 * Mirrors useIntegrationAccounts.ts conventions:
 *   · const KEY per query key
 *   · api.get / api.post / api.patch / api.delete from @noctusai/seed/infra
 *   · mutations invalidate their relevant keys on success
 *
 * API contract: all endpoints return bare arrays/objects (NO envelope).
 * GET /api/marcas → Marca[]
 * GET /api/marcas/{id} → Marca
 * POST /api/marcas { slug, name, kind?, notes? } → Marca
 * PATCH /api/marcas/{id} → Marca
 * DELETE /api/marcas/{id} → 204
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

// ─── Types ──────────────────────────────────────────────────────────────────

export interface Marca {
  id: string;
  org_id: string;
  slug: string;
  name: string;
  kind: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateClientInput {
  slug: string;
  name: string;
  kind?: string;
  notes?: string;
}

export interface UpdateClientInput {
  slug?: string;
  name?: string;
  kind?: string | null;
  notes?: string | null;
}

// ─── Query keys ─────────────────────────────────────────────────────────────

const CLIENTS_KEY = ["sw", "clients"] as const;
const MARCA_KEY = (id: string) => ["sw", "clients", "detail", id] as const;

// ─── Queries ─────────────────────────────────────────────────────────────────

export function useMarcas() {
  return useQuery({
    queryKey: CLIENTS_KEY,
    queryFn: async () => {
      const res = await api.get<Marca[]>("/api/marcas");
      return res ?? [];
    },
  });
}

export function useMarca(id: string) {
  return useQuery({
    queryKey: MARCA_KEY(id),
    queryFn: () => api.get<Marca>(`/api/marcas/${id}`),
    enabled: !!id,
  });
}

// ─── Mutations ───────────────────────────────────────────────────────────────

const byName = (a: Marca, b: Marca) => a.name.localeCompare(b.name);

export function useCreateMarca() {
  return useCacheWriteMutation<Marca, CreateClientInput>({
    mutationFn: (payload) => api.post<Marca>("/api/marcas", payload),
    targets: [
      {
        queryKey: CLIENTS_KEY,
        // The list is ordered by name server-side; put the new row where the settle refetch will.
        commit: (old: Marca[] | undefined, saved) =>
          listOps.insertSorted(old, saved, byName),
      },
    ],
  });
}

export function useUpdateMarca() {
  return useCacheWriteMutation<Marca, UpdateClientInput & { id: string }>({
    mutationFn: ({ id, ...payload }) => api.patch<Marca>(`/api/marcas/${id}`, payload),
    targets: ({ id, ...changes }) => [
      {
        queryKey: CLIENTS_KEY,
        optimistic: (old: Marca[] | undefined) => listOps.patch(old, id, changes as Partial<Marca>),
        // A rename moves the row to where the server's name order puts it.
        commit: (old: Marca[] | undefined, saved) => listOps.insertSorted(old, saved, byName),
      },
      {
        queryKey: MARCA_KEY(id),
        optimistic: (old: Marca | undefined) => listOps.merge(old, changes as Partial<Marca>),
        commit: (_old: Marca | undefined, saved) => saved,
      },
    ],
  });
}

export function useDeleteMarca() {
  return useCacheWriteMutation<unknown, string>({
    mutationFn: (id) => api.delete(`/api/marcas/${id}`),
    targets: [
      {
        queryKey: CLIENTS_KEY,
        optimistic: (old: Marca[] | undefined, id) => listOps.remove(old, id),
      },
    ],
  });
}
