import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, useAuthStore } from '@noctusai/seed/infra';
import { toast } from "sonner";
import type { Carteira } from "@/types";

export function useCarteiras() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["carteiras"],
    queryFn: async () => {
      const result = await api.get("/api/carteiras");
      return (result.data || []) as Carteira[];
    },
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
  });
}

export function useCarteira(id?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["carteira", id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/carteiras/${id}`);
      return result.data as Carteira;
    },
    enabled: !!user && !!id,
    staleTime: 5 * 60 * 1000,
  });
}

export function useCarteiraResumo(id?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["carteira", id, "resumo"],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/carteiras/${id}/resumo`);
      return result.data;
    },
    enabled: !!user && !!id,
    staleTime: 2 * 60 * 1000,
  });
}

export function useCreateCarteira() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: Partial<Carteira>) => {
      const result = await api.post("/api/carteiras", data);
      return result.data as Carteira;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["carteiras"] });
      // Dropped "dashboard" + "patrimonio" — a new carteira has zero
      // ativos (CarteiraService.criar only inserts the carteiras row; no
      // holding is created alongside it), so DashboardService.kpis
      // (which sums ativos.*) and PatrimonioService.calcular_atual
      // (same) cannot have moved.
      toast.success("Carteira criada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao criar carteira", { description: error.message });
    },
  });
}

export function useUpdateCarteira() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: Partial<Carteira> & { id: string }) => {
      const result = await api.patch(`/api/carteiras/${id}`, data);
      return result.data as Carteira;
    },
    onSuccess: (carteira) => {
      // Direct patch — CarteiraDetalhes.tsx reads `useCarteira(id)`
      // independently of the "carteiras" list, and this mutation is
      // fired from the LIST page (Carteira.tsx), so the singular query
      // was never invalidated before: renaming a portfolio there left a
      // stale name on its own detail page for up to its 5-minute
      // staleTime. The response already carries the full updated row.
      queryClient.setQueryData(["carteira", carteira.id], carteira);
      queryClient.invalidateQueries({ queryKey: ["carteiras"] });
      // Dropped "dashboard" + "patrimonio" — CarteiraService.atualizar
      // only patches carteiras columns (nome/etc.), never touches
      // ativos, so neither aggregate can have moved.
      toast.success("Carteira atualizada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao atualizar carteira", { description: error.message });
    },
  });
}

export function useDeleteCarteira() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/carteiras/${id}`);
    },
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: ["carteiras"] });
      // KEPT, unlike create/update — `ativos.carteira_id` is
      // `REFERENCES carteiras(id) ON DELETE CASCADE` (migration
      // 001_personal_finance.sql), so deleting a carteira deletes every
      // holding in it. That genuinely moves DashboardService.kpis
      // (ativos sums) and PatrimonioService.calcular_atual — narrowed
      // to "atual" only, "historico" stays snapshot-only.
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["patrimonio", "atual"] });
      // Purge — the carteira (and its cascaded ativos) are gone, so a
      // refetch of `["carteira", id]` would just 404.
      queryClient.removeQueries({ queryKey: ["carteira", id] });
      toast.success("Carteira excluida com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao excluir carteira", { description: error.message });
    },
  });
}
