/**
 * useClients — TanStack Query hooks for /api/clients (Orbity CRM).
 *
 * Mirrors the orbity backend contract exactly:
 *   GET    /api/clients          → list (paginated, active_only)
 *   POST   /api/clients          → create → 201 ClientOut
 *   GET    /api/clients/{id}     → detail ClientOut
 *   PATCH  /api/clients/{id}     → update ClientOut
 *   POST   /api/clients/{id}/archive → soft-delete
 */
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api";

// ─── Types (mirror backend schemas/clients.py) ──────────────────────────────

export interface Client {
  id: string;
  org_id: string;
  name: string;
  email: string | null;
  phone: string | null;
  company: string | null;
  monthly_value: number | null;
  due_date: number | null;
  active: boolean;
  default_billing_type: string | null;
  billing_automation_enabled: boolean;
  report_token: string | null;
  created_at: string;
  updated_at: string;
}

export interface ClientListResponse {
  items: Client[];
  total: number;
  page: number;
  page_size: number;
}

export interface ClientCreate {
  name: string;
  email?: string;
  phone?: string;
  company?: string;
  monthly_value?: number;
  due_date?: number;
  default_billing_type?: string;
  billing_automation_enabled?: boolean;
}

export interface ClientUpdate extends Partial<ClientCreate> {
  active?: boolean;
}

// ─── Query keys ─────────────────────────────────────────────────────────────

export const clientKeys = {
  all: ["clients"] as const,
  list: (params?: Record<string, unknown>) =>
    ["clients", "list", params] as const,
  detail: (id: string) => ["clients", "detail", id] as const,
};

// ─── List ────────────────────────────────────────────────────────────────────

export function useClients(
  params: { active_only?: boolean; page?: number; page_size?: number } = {}
) {
  const { active_only = true, page = 1, page_size = 50 } = params;
  return useQuery({
    queryKey: clientKeys.list({ active_only, page, page_size }),
    queryFn: async () => {
      const result = await api.get<ClientListResponse>("/api/clients", {
        active_only,
        page,
        page_size,
      });
      return result;
    },
    staleTime: 2 * 60 * 1000,
  });
}

// ─── Detail ──────────────────────────────────────────────────────────────────

export function useClient(id?: string) {
  return useQuery({
    queryKey: clientKeys.detail(id ?? ""),
    queryFn: async () => {
      const result = await api.get<Client>(`/api/clients/${id}`);
      return result;
    },
    enabled: !!id,
    staleTime: 5 * 60 * 1000,
  });
}

// ─── Create ──────────────────────────────────────────────────────────────────

export function useCreateClient() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ClientCreate) =>
      api.post<Client>("/api/clients", payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: clientKeys.all });
      toast.success("Cliente criado com sucesso");
    },
    onError: () => {
      toast.error("Falha ao criar cliente");
    },
  });
}

// ─── Update ──────────────────────────────────────────────────────────────────

export function useUpdateClient() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: ClientUpdate }) =>
      api.patch<Client>(`/api/clients/${id}`, data),
    onSuccess: (_result, variables) => {
      qc.invalidateQueries({ queryKey: clientKeys.all });
      qc.invalidateQueries({ queryKey: clientKeys.detail(variables.id) });
      toast.success("Cliente atualizado");
    },
    onError: () => {
      toast.error("Falha ao atualizar cliente");
    },
  });
}

// ─── Archive (soft-delete) ───────────────────────────────────────────────────

export function useArchiveClient() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api.post<{ ok: boolean; id: string }>(`/api/clients/${id}/archive`, {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: clientKeys.all });
      toast.success("Cliente arquivado");
    },
    onError: () => {
      toast.error("Falha ao arquivar cliente");
    },
  });
}
