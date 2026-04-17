import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, useAuthStore } from '@noctusai/seed/infra';
import { toast } from "sonner";
import type { Cotacao } from "@/types";

export function useCotacao(ticker?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["cotacao", ticker],
    queryFn: async () => {
      if (!ticker) return null;
      const result = await api.get(`/api/cotacoes/${ticker}`);
      return result.data as Cotacao;
    },
    enabled: !!user && !!ticker,
    staleTime: 1 * 60 * 1000,
  });
}

export function useAtualizarPrecos() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const result = await api.post("/api/cotacoes/atualizar");
      return result.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cotacao"] });
      queryClient.invalidateQueries({ queryKey: ["ativos"] });
      queryClient.invalidateQueries({ queryKey: ["carteiras"] });
      queryClient.invalidateQueries({ queryKey: ["carteira"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["patrimonio"] });
      toast.success("Precos atualizados com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao atualizar precos", { description: error.message });
    },
  });
}
