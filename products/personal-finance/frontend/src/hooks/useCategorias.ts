import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, useAuthStore } from '@noctusai/seed/infra';
import { toast } from "sonner";
import type { Categoria } from "@/types";

export function useCategorias(tipo?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["categorias", tipo],
    queryFn: async () => {
      const params: { tipo?: string } = {};
      if (tipo) params.tipo = tipo;
      const result = await api.get("/api/categorias", params);
      return (result.data || []) as Categoria[];
    },
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
  });
}

export function useCategoriasArvore(tipo?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["categorias", "arvore", tipo],
    queryFn: async () => {
      const params: { tipo?: string } = {};
      if (tipo) params.tipo = tipo;
      const result = await api.get("/api/categorias/arvore", params);
      return (result.data || []) as Categoria[];
    },
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
  });
}

export function useCreateCategoria() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: Partial<Categoria>) => {
      const result = await api.post("/api/categorias", data);
      return result.data as Categoria;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["categorias"] });
      toast.success("Categoria criada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao criar categoria", { description: error.message });
    },
  });
}

export function useUpdateCategoria() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: Partial<Categoria> & { id: string }) => {
      const result = await api.patch(`/api/categorias/${id}`, data);
      return result.data as Categoria;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["categorias"] });
      queryClient.invalidateQueries({ queryKey: ["transacoes"] });
      queryClient.invalidateQueries({ queryKey: ["orcamentos"] });
      toast.success("Categoria atualizada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao atualizar categoria", { description: error.message });
    },
  });
}

export function useDeleteCategoria() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/categorias/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["categorias"] });
      toast.success("Categoria excluida com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao excluir categoria", { description: error.message });
    },
  });
}
