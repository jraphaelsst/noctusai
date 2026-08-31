import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, useAuthStore } from '@noctusai/seed/infra';
import { toast } from "sonner";
import type { Ativo } from "@/types";

export function useAtivos(carteiraId?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["ativos", carteiraId],
    queryFn: async () => {
      const params: { carteira_id?: string } = {};
      if (carteiraId) params.carteira_id = carteiraId;
      const result = await api.get("/api/ativos", params);
      return (result.data || []) as Ativo[];
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useAtivo(id?: string) {
  return useQuery({
    queryKey: ["ativo", id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/ativos/${id}`);
      return result.data as Ativo;
    },
    enabled: !!id,
    staleTime: 5 * 60 * 1000,
  });
}

export function useCreateAtivo() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: Partial<Ativo>) => {
      const result = await api.post("/api/ativos", data);
      return result.data as Ativo;
    },
    onSuccess: () => {
      // "ativos"/"carteiras"/"carteira"/"dashboard" all KEPT broad:
      // CarteiraService.listar() enriches every carteira with
      // valor_total/ganho_perda_total/total_ativos computed live from
      // "ativos" (same for CarteiraService.resumo()'s allocation), and
      // DashboardService.kpis() sums ativos.valor_atual/ganho_perda
      // directly — an ativo write legitimately moves all four.
      queryClient.invalidateQueries({ queryKey: ["ativos"] });
      queryClient.invalidateQueries({ queryKey: ["carteiras"] });
      queryClient.invalidateQueries({ queryKey: ["carteira"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      // Narrowed to "atual" — PatrimonioService.calcular_atual() sums
      // ativos.valor_atual live; "historico" is immutable snapshot rows
      // only useCriarSnapshot (usePatrimonio.ts) writes.
      queryClient.invalidateQueries({ queryKey: ["patrimonio", "atual"] });
      toast.success("Ativo adicionado com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao adicionar ativo", { description: error.message });
    },
  });
}

export function useUpdateAtivo() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: Partial<Ativo> & { id: string }) => {
      const result = await api.patch(`/api/ativos/${id}`, data);
      return result.data as Ativo;
    },
    onSuccess: () => {
      // Same set as useCreateAtivo — see its comment. "patrimonio"
      // narrowed to "atual" for the same reason.
      queryClient.invalidateQueries({ queryKey: ["ativos"] });
      queryClient.invalidateQueries({ queryKey: ["carteiras"] });
      queryClient.invalidateQueries({ queryKey: ["carteira"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["patrimonio", "atual"] });
      toast.success("Ativo atualizado com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao atualizar ativo", { description: error.message });
    },
  });
}

export function useDeleteAtivo() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/ativos/${id}`);
    },
    onSuccess: () => {
      // Same set as useCreateAtivo — see its comment. "patrimonio"
      // narrowed to "atual" for the same reason.
      queryClient.invalidateQueries({ queryKey: ["ativos"] });
      queryClient.invalidateQueries({ queryKey: ["carteiras"] });
      queryClient.invalidateQueries({ queryKey: ["carteira"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["patrimonio", "atual"] });
      toast.success("Ativo removido com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao remover ativo", { description: error.message });
    },
  });
}
