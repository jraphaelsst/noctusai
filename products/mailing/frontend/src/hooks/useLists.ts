import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useAuthStore } from "@/store/authStore";

export interface ContactList {
  id: string;
  nome: string;
  descricao?: string;
  tipo: "static" | "dynamic";
  filtros: Record<string, any>;
  contact_count: number;
  created_at: string;
}

export function useLists() {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: ["lists"],
    queryFn: () => api.get("/api/lists"),
    enabled: !!user,
  });
}

export function useList(id: string) {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: ["list", id],
    queryFn: () => api.get(`/api/lists/${id}`),
    enabled: !!user && !!id,
  });
}

export function useListContacts(id: string) {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: ["list-contacts", id],
    queryFn: () => api.get(`/api/lists/${id}/contacts`),
    enabled: !!user && !!id,
  });
}

export function useCreateList() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<ContactList>) => api.post("/api/lists", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["lists"] }),
  });
}

export function useUpdateList() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: { id: string } & Partial<ContactList>) =>
      api.patch(`/api/lists/${id}`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["lists"] }),
  });
}

export function useDeleteList() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/lists/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["lists"] }),
  });
}

export function useAddMembers() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ listId, contactIds }: { listId: string; contactIds: string[] }) =>
      api.post(`/api/lists/${listId}/members`, { contact_ids: contactIds }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["lists"] });
      qc.invalidateQueries({ queryKey: ["list-contacts"] });
    },
  });
}
