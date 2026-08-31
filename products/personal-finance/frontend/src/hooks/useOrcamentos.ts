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
    placeholderData: (prev) => prev,
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
      // Dropped "dashboard" — grepped DashboardService (kpis + resumo):
      // it reads patrimonio, relatorios/mensal and ativos, never the
      // orcamentos/orcamento_itens tables. A budget CRUD cannot change
      // any dashboard number; this invalidation never did anything but
      // force a wasted refetch.
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
    onSuccess: (orcamento) => {
      // Direct patch — the response carries the full row, and
      // OrcamentoDetalhes.tsx reads `useOrcamento(id)` on the SAME page
      // this mutation fires from; without this the page didn't reflect
      // its own rename/period edit until an unrelated refetch happened.
      queryClient.setQueryData(["orcamento", orcamento.id], orcamento);
      queryClient.invalidateQueries({ queryKey: ["orcamentos"] });
      // "dashboard" dropped — see useCreateOrcamento's comment.
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
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: ["orcamentos"] });
      // Purge, don't invalidate — the row is gone, so a refetch of
      // `["orcamento", id]` (OrcamentoDetalhes.tsx navigates away on
      // success, but a second tab may not) would just 404.
      queryClient.removeQueries({ queryKey: ["orcamento", id] });
      // "dashboard" dropped — see useCreateOrcamento's comment.
      toast.success("Orcamento excluido com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao excluir orcamento", { description: error.message });
    },
  });
}

/**
 * Item mutations (wave-2 narrowing): "orcamento" (singular family — covers
 * `["orcamento", id]` AND `["orcamento", id, "progresso", mes]`) is the
 * ONLY key an item write can affect — `orcamento_itens` rows never change
 * the parent `Orcamento` row (nome/metodo/periodo/ativo), so "orcamentos"
 * (the plain list) is dropped. "dashboard" dropped for the same reason as
 * the orcamento CRUD above — DashboardService never reads orcamento data.
 */
export function useCreateOrcamentoItem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ orcamentoId, ...data }: { orcamentoId: string; categoria_id: string; valor_planejado: number; periodo_mes: string }) => {
      const result = await api.post(`/api/orcamentos/${orcamentoId}/itens`, data);
      return result.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["orcamento"] });
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
      toast.success("Item removido com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao remover item", { description: error.message });
    },
  });
}
