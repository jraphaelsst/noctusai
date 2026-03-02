import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useAuthStore } from "@/store/authStore";

export function useRelatorioMensal(mes?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["relatorios", "mensal", mes],
    queryFn: async () => {
      if (!mes) return null;
      const result = await api.get("/api/relatorios/mensal", { mes });
      return result.data;
    },
    enabled: !!user && !!mes,
    staleTime: 5 * 60 * 1000,
  });
}

export function useRelatorioAnual(ano?: number) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["relatorios", "anual", ano],
    queryFn: async () => {
      if (!ano) return null;
      const result = await api.get("/api/relatorios/anual", { ano });
      return result.data;
    },
    enabled: !!user && !!ano,
    staleTime: 5 * 60 * 1000,
  });
}

export function useFluxoCaixa(dataInicio?: string, dataFim?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["relatorios", "fluxo-caixa", dataInicio, dataFim],
    queryFn: async () => {
      if (!dataInicio || !dataFim) return null;
      const result = await api.get("/api/relatorios/fluxo-caixa", {
        data_inicio: dataInicio,
        data_fim: dataFim,
      });
      return result.data;
    },
    enabled: !!user && !!dataInicio && !!dataFim,
    staleTime: 5 * 60 * 1000,
  });
}
