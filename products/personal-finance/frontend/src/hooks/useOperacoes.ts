import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useAuthStore } from "@/store/authStore";
import { toast } from "sonner";
import type { Operacao } from "@/types";

interface FiltrosOperacoes {
  carteira_id?: string;
  ativo_id?: string;
  ticker?: string;
  page?: number;
  page_size?: number;
}

export function useOperacoes(filtros?: FiltrosOperacoes) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["operacoes", filtros],
    queryFn: async () => {
      const params: Record<string, any> = {};
      if (filtros?.carteira_id) params.carteira_id = filtros.carteira_id;
      if (filtros?.ativo_id) params.ativo_id = filtros.ativo_id;
      if (filtros?.ticker) params.ticker = filtros.ticker;
      if (filtros?.page) params.page = filtros.page;
      if (filtros?.page_size) params.page_size = filtros.page_size;
      const result = await api.get("/api/operacoes", params);
      return (result.data || []) as Operacao[];
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useCreateOperacao() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: Partial<Operacao>) => {
      const result = await api.post("/api/operacoes", data);
      return result.data as Operacao;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["operacoes"] });
      queryClient.invalidateQueries({ queryKey: ["ativos"] });
      queryClient.invalidateQueries({ queryKey: ["carteiras"] });
      queryClient.invalidateQueries({ queryKey: ["carteira"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["patrimonio"] });
      toast.success("Operacao registrada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao registrar operacao", { description: error.message });
    },
  });
}

export function useDeleteOperacao() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/operacoes/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["operacoes"] });
      queryClient.invalidateQueries({ queryKey: ["ativos"] });
      queryClient.invalidateQueries({ queryKey: ["carteiras"] });
      queryClient.invalidateQueries({ queryKey: ["carteira"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["patrimonio"] });
      toast.success("Operacao excluida com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao excluir operacao", { description: error.message });
    },
  });
}
