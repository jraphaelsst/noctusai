import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, useAuthStore } from '@noctusai/seed/infra';
import { toast } from "sonner";
import type { Orcamento } from "@/types";

export function useOrcamentos() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["orcamentos"],
    queryFn: async () => {
      const result = await api.get("/api/orcamentos");
      return (result.data || []) as Orcamento[];
    },
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
  });
}

export function useOrcamento(id?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["orcamento", id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/orcamentos/${id}`);
      return result.data as Orcamento;
    },
    enabled: !!user && !!id,
    staleTime: 5 * 60 * 1000,
  });
}

export function useOrcamentoProgresso(id?: string, periodoMes?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["orcamento", id, "progresso", periodoMes],
    queryFn: async () => {
      if (!id) return null;
      const params: { periodo_mes?: string } = {};
      if (periodoMes) params.periodo_mes = periodoMes;
      const result = await api.get(`/api/orcamentos/${id}/progresso`, params);
      return result.data;
    },
    enabled: !!user && !!id,
    staleTime: 2 * 60 * 1000,
  });
}

export function useCreateOrcamento() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: Partial<Orcamento>) => {
      const result = await api.post("/api/orcamentos", data);
      return result.data as Orcamento;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["orcamentos"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success("Orcamento criado com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao criar orcamento", { description: error.message });
    },
  });
}

export function useUpdateOrcamento() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: Partial<Orcamento> & { id: string }) => {
      const result = await api.patch(`/api/orcamentos/${id}`, data);
      return result.data as Orcamento;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["orcamentos"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success("Orcamento atualizado com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao atualizar orcamento", { description: error.message });
    },
  });
}

export function useDeleteOrcamento() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/orcamentos/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["orcamentos"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success("Orcamento excluido com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao excluir orcamento", { description: error.message });
    },
  });
}

export function useCreateOrcamentoItem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ orcamentoId, ...data }: { orcamentoId: string; categoria_id: string; valor_planejado: number; periodo_mes: string }) => {
      const result = await api.post(`/api/orcamentos/${orcamentoId}/itens`, data);
      return result.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["orcamento"] });
      queryClient.invalidateQueries({ queryKey: ["orcamentos"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success("Item adicionado com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao adicionar item", { description: error.message });
    },
  });
}

export function useUpdateOrcamentoItem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ itemId, ...data }: { itemId: string; valor_planejado?: number }) => {
      const result = await api.patch(`/api/orcamentos/itens/${itemId}`, data);
      return result.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["orcamento"] });
      queryClient.invalidateQueries({ queryKey: ["orcamentos"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success("Item atualizado com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao atualizar item", { description: error.message });
    },
  });
}

export function useDeleteOrcamentoItem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (itemId: string) => {
      await api.delete(`/api/orcamentos/itens/${itemId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["orcamento"] });
      queryClient.invalidateQueries({ queryKey: ["orcamentos"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success("Item removido com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao remover item", { description: error.message });
    },
  });
}
