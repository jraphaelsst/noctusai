import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useAuthStore } from "@/store/authStore";
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
  return useQuery({
    queryKey: ["carteira", id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/carteiras/${id}`);
      return result.data as Carteira;
    },
    enabled: !!id,
    staleTime: 5 * 60 * 1000,
  });
}

export function useCarteiraResumo(id?: string) {
  return useQuery({
    queryKey: ["carteira", id, "resumo"],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/carteiras/${id}/resumo`);
      return result.data;
    },
    enabled: !!id,
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
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["patrimonio"] });
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["carteiras"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["patrimonio"] });
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["carteiras"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["patrimonio"] });
      toast.success("Carteira excluida com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao excluir carteira", { description: error.message });
    },
  });
}
