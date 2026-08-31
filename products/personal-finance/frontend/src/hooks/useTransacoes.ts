import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, useAuthStore } from '@noctusai/seed/infra';
import { toast } from "sonner";
import type { Transacao } from "@/types";

interface FiltrosTransacoes {
  page?: number;
  page_size?: number;
  conta_id?: string;
  categoria_id?: string;
  tipo?: string;
  data_inicio?: string;
  data_fim?: string;
  busca?: string;
}

export function useTransacoes(filtros?: FiltrosTransacoes) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["transacoes", filtros],
    queryFn: async () => {
      const params: FiltrosTransacoes = {};
      if (filtros?.page) params.page = filtros.page;
      if (filtros?.page_size) params.page_size = filtros.page_size;
      if (filtros?.conta_id) params.conta_id = filtros.conta_id;
      if (filtros?.categoria_id) params.categoria_id = filtros.categoria_id;
      if (filtros?.tipo) params.tipo = filtros.tipo;
      if (filtros?.data_inicio) params.data_inicio = filtros.data_inicio;
      if (filtros?.data_fim) params.data_fim = filtros.data_fim;
      if (filtros?.busca) params.busca = filtros.busca;
      const result = await api.get("/api/transacoes", params);
      return result as { data: Transacao[]; total: number; page: number; page_size: number };
    },
    placeholderData: (prev) => prev,
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useTransacao(id?: string) {
  return useQuery({
    queryKey: ["transacao", id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/transacoes/${id}`);
      return result.data as Transacao;
    },
    enabled: !!id,
    staleTime: 5 * 60 * 1000,
  });
}

export function useTransacoesPorCategoria(dataInicio?: string, dataFim?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["transacoes", "por-categoria", dataInicio, dataFim],
    queryFn: async () => {
      const params: { data_inicio?: string; data_fim?: string } = {};
      if (dataInicio) params.data_inicio = dataInicio;
      if (dataFim) params.data_fim = dataFim;
      const result = await api.get("/api/transacoes/por-categoria", params);
      return result.data;
    },
    enabled: !!user && !!dataInicio && !!dataFim,
    staleTime: 3 * 60 * 1000,
  });
}

export function useCreateTransacao() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: Partial<Transacao>) => {
      const result = await api.post("/api/transacoes", data);
      return result.data as Transacao;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["transacoes"] });
      queryClient.invalidateQueries({ queryKey: ["contas"] });
      queryClient.invalidateQueries({ queryKey: ["orcamentos"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["relatorios"] });
      queryClient.invalidateQueries({ queryKey: ["patrimonio"] });
      toast.success("Transacao criada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao criar transacao", { description: error.message });
    },
  });
}

export function useUpdateTransacao() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: Partial<Transacao> & { id: string }) => {
      const result = await api.patch(`/api/transacoes/${id}`, data);
      return result.data as Transacao;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["transacoes"] });
      queryClient.invalidateQueries({ queryKey: ["contas"] });
      queryClient.invalidateQueries({ queryKey: ["orcamentos"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["relatorios"] });
      queryClient.invalidateQueries({ queryKey: ["patrimonio"] });
      toast.success("Transacao atualizada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao atualizar transacao", { description: error.message });
    },
  });
}

export function useDeleteTransacao() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/transacoes/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["transacoes"] });
      queryClient.invalidateQueries({ queryKey: ["contas"] });
      queryClient.invalidateQueries({ queryKey: ["orcamentos"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["relatorios"] });
      queryClient.invalidateQueries({ queryKey: ["patrimonio"] });
      toast.success("Transacao excluida com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao excluir transacao", { description: error.message });
    },
  });
}
