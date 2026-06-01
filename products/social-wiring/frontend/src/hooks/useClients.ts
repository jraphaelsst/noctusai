/**
 * Clients hooks — TanStack Query wrappers for the client entity CRUD.
 * Mirrors useIntegrationAccounts.ts conventions:
 *   · const KEY per query key
 *   · api.get / api.post / api.patch / api.delete from @noctusai/seed/infra
 *   · mutations invalidate their relevant keys on success
 *
 * API contract: all endpoints return bare arrays/objects (NO envelope).
 * GET /api/clients → Client[]
 * POST /api/clients { slug, name, kind?, notes? } → Client
 * PATCH /api/clients/{id} → Client
 * DELETE /api/clients/{id} → 204
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

// ─── Types ──────────────────────────────────────────────────────────────────

export interface Client {
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

export function useClients() {
  return useQuery({
    queryKey: CLIENTS_KEY,
    queryFn: async () => {
      const res = await api.get<Client[]>("/api/clients");
      return res ?? [];
    },
  });
}

export function useClient(id: string) {
  return useQuery({
    queryKey: CLIENT_KEY(id),
    queryFn: async () => {
      const res = await api.get<Client>(`/api/clients/${id}`);
      return res;
    },
    enabled: !!id,
  });
}

// ─── Mutations ───────────────────────────────────────────────────────────────

export function useCreateClient() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateClientInput) =>
      api.post<Client>("/api/clients", payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CLIENTS_KEY });
    },
  });
}

export function useUpdateClient() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...payload }: UpdateClientInput & { id: string }) =>
      api.patch<Client>(`/api/clients/${id}`, payload),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: CLIENTS_KEY });
      if ((res as any)?.id) {
        qc.invalidateQueries({ queryKey: CLIENT_KEY((res as any).id) });
      }
    },
  });
}

export function useDeleteClient() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/clients/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CLIENTS_KEY });
    },
  });
}
