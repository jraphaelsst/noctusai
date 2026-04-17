import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuthStore, api } from '@noctusai/seed/infra';
import { toast } from "sonner";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface Nota {
  id: string;
  titulo: string;
  conteudo?: string;
  categoria?: string;
  tags: string[];
  fixada: boolean;
  created_at: string;
  updated_at: string;
}

export interface PaginatedNotaResponse {
  data: Nota[];
  pagination: {
    page: number;
    page_size: number;
    total: number;
    total_pages: number;
  };
}

export interface NotaForm {
  titulo: string;
  conteudo: string;
  tags: string;
  fixada: boolean;
  categoria: string;
}

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

export function useNotas(busca: string, page: number, pageSize: number) {
  const { user } = useAuthStore();

  const queryParams = new URLSearchParams();
  queryParams.set("page", String(page));
  queryParams.set("page_size", String(pageSize));
  if (busca) queryParams.set("busca", busca);

  return useQuery<PaginatedNotaResponse>({
    queryKey: ["notas", busca, page],
    queryFn: () => api.get(`/api/notes?${queryParams.toString()}`),
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useCreateNota(onSuccess?: () => void) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post("/api/notes", body),
    onSuccess: () => {
      toast.success("Nota criada com sucesso");
      queryClient.invalidateQueries({ queryKey: ["notas"] });
      onSuccess?.();
    },
    onError: (err: any) => toast.error("Erro ao criar nota", { description: err?.message }),
  });
}

export function useUpdateNota(onSuccess?: () => void) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      api.patch(`/api/notes/${id}`, body),
    onSuccess: () => {
      toast.success("Nota atualizada");
      queryClient.invalidateQueries({ queryKey: ["notas"] });
      onSuccess?.();
    },
    onError: (err: any) => toast.error("Erro ao atualizar nota", { description: err?.message }),
  });
}

export function useDeleteNota(onSuccess?: () => void) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/notes/${id}`),
    onSuccess: () => {
      toast.success("Nota removida");
      queryClient.invalidateQueries({ queryKey: ["notas"] });
      onSuccess?.();
    },
    onError: (err: any) => toast.error("Erro ao remover nota", { description: err?.message }),
  });
}

export function usePinNota() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, fixada }: { id: string; fixada: boolean }) =>
      api.patch(`/api/notes/${id}`, { fixada }),
    onSuccess: (_data, vars) => {
      toast.success(vars.fixada ? "Nota fixada" : "Nota desafixada");
      queryClient.invalidateQueries({ queryKey: ["notas"] });
    },
    onError: (err: any) => toast.error("Erro ao fixar nota", { description: err?.message }),
  });
}
