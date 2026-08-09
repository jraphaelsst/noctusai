/**
 * Clients hooks — TanStack Query wrappers for the client entity CRUD.
 * Mirrors useIntegrationAccounts.ts conventions:
 *   · const KEY per query key
 *   · api.get / api.post / api.patch / api.delete from @noctusai/seed/infra
 *   · mutations invalidate their relevant keys on success
 *
 * API contract: all endpoints return bare arrays/objects (NO envelope).
 * GET /api/marcas → Marca[]
 * POST /api/marcas { slug, name, kind?, notes? } → Marca
 * PATCH /api/marcas/{id} → Marca
 * DELETE /api/marcas/{id} → 204
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

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
const CLIENT_KEY = (id: string) => ["sw", "clients", "detail", id] as const;

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

export function useClient(id: string) {
  return useQuery({
    queryKey: CLIENT_KEY(id),
    queryFn: async () => {
      const res = await api.get<Marca>(`/api/marcas/${id}`);
      return res;
    },
    enabled: !!id,
  });
}

// ─── Mutations ───────────────────────────────────────────────────────────────

export function useCreateMarca() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateClientInput) =>
      api.post<Marca>("/api/marcas", payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CLIENTS_KEY });
    },
  });
}

export function useUpdateMarca() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...payload }: UpdateClientInput & { id: string }) =>
      api.patch<Marca>(`/api/marcas/${id}`, payload),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: CLIENTS_KEY });
      if ((res as any)?.id) {
        qc.invalidateQueries({ queryKey: CLIENT_KEY((res as any).id) });
      }
    },
  });
}

export function useDeleteMarca() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/marcas/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CLIENTS_KEY });
    },
  });
}
