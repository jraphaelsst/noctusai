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
      // "transacoes" — TransacoesService joins
      // `categoria:categorias(id,nome,icone,cor)` into every list row, so
      // renaming/recoloring a categoria changes what the transações list
      // displays even though no transação row itself changed.
      queryClient.invalidateQueries({ queryKey: ["transacoes"] });
      // "orcamento" (singular family), NOT "orcamentos" (the plain list)
      // — same wrong-key shape as useTransacoes.ts: OrcamentosService's
      // item query also joins `categoria:categorias(id,nome,icone,cor)`,
      // which `useOrcamentoProgresso` reads under "orcamento". The
      // `Orcamento` rows themselves never embed categoria fields, so
      // "orcamentos" here never refreshed anything real.
      queryClient.invalidateQueries({ queryKey: ["orcamento"] });
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
