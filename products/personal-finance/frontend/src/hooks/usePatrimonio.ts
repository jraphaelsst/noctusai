import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, useAuthStore } from '@noctusai/seed/infra';
import { toast } from "sonner";
import type { PatrimonioSnapshot } from "@/types";

export function usePatrimonioAtual() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["patrimonio", "atual"],
    queryFn: async () => {
      const result = await api.get("/api/patrimonio/atual");
      return result.data as PatrimonioSnapshot;
    },
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
  });
}

export function usePatrimonioHistorico(limite?: number) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["patrimonio", "historico", limite],
    queryFn: async () => {
      const params: { limite?: number } = {};
      if (limite !== undefined) params.limite = limite;
      const result = await api.get("/api/patrimonio/historico", params);
      return (result.data || []) as PatrimonioSnapshot[];
    },
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
  });
}

export function useCriarSnapshot() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const result = await api.post("/api/patrimonio/snapshot");
      return result.data as PatrimonioSnapshot;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["patrimonio"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success("Snapshot de patrimonio criado com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao criar snapshot", { description: error.message });
    },
  });
}
