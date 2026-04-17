import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, useAuthStore } from '@noctusai/seed/infra';

export interface Contact {
  id: string;
  email: string;
  nome?: string;
  telefone?: string;
  empresa?: string;
  tags: string[];
  custom_fields: Record<string, any>;
  source: string;
  status: "active" | "unsubscribed" | "bounced" | "complained";
  created_at: string;
  updated_at: string;
}

export function useContacts(page = 1, pageSize = 20, filters?: { status?: string; search?: string }) {
  const { user } = useAuthStore();
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (filters?.status) params.set("status", filters.status);
  if (filters?.search) params.set("search", filters.search);

  return useQuery({
    queryKey: ["contacts", page, pageSize, filters],
    queryFn: () => api.get(`/api/contacts?${params}`),
    enabled: !!user,
  });
}

export function useContact(id: string) {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: ["contact", id],
    queryFn: () => api.get(`/api/contacts/${id}`),
    enabled: !!user && !!id,
  });
}

export function useCreateContact() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<Contact>) => api.post("/api/contacts", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["contacts"] }),
  });
}

export function useUpdateContact() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: { id: string } & Partial<Contact>) =>
      api.patch(`/api/contacts/${id}`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["contacts"] }),
  });
}

export function useDeleteContact() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/contacts/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["contacts"] }),
  });
}

export function useImportContacts() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (contacts: Partial<Contact>[]) => api.post("/api/contacts/import", { contacts }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["contacts"] }),
  });
}
