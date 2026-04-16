import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useAuthStore } from "@/store/authStore";

export interface Template {
  id: string;
  nome: string;
  assunto: string;
  corpo_html: string;
  corpo_text?: string;
  variaveis: string[];
  categoria: "marketing" | "transactional" | "follow_up" | "newsletter";
  ativo: boolean;
  created_at: string;
}

export function useTemplates(categoria?: string) {
  const { user } = useAuthStore();
  const params = categoria ? `?categoria=${categoria}` : "";
  return useQuery({
    queryKey: ["templates", categoria],
    queryFn: () => api.get(`/api/templates${params}`),
    enabled: !!user,
  });
}

export function useTemplate(id: string) {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: ["template", id],
    queryFn: () => api.get(`/api/templates/${id}`),
    enabled: !!user && !!id,
  });
}

export function useCreateTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<Template>) => api.post("/api/templates", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["templates"] }),
  });
}

export function useUpdateTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: { id: string } & Partial<Template>) =>
      api.patch(`/api/templates/${id}`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["templates"] }),
  });
}

export function useDeleteTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/templates/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["templates"] }),
  });
}

export function usePreviewTemplate() {
  return useMutation({
    mutationFn: ({ id, variaveis }: { id: string; variaveis: Record<string, string> }) =>
      api.post(`/api/templates/${id}/preview`, { variaveis }),
  });
}
