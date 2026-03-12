import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useAuthStore } from "@/store/authStore";
import { toast } from "sonner";
import type { Conta } from "@/types";

export function useContas(ativo?: boolean) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["contas", ativo],
    queryFn: async () => {
      const params: Record<string, any> = {};
      if (ativo !== undefined) params.ativo = ativo;
      const result = await api.get("/api/contas", params);
      return (result.data || []) as Conta[];
    },
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
  });
}

export function useConta(id?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["conta", id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/contas/${id}`);
      return result.data as Conta;
    },
    enabled: !!user && !!id,
    staleTime: 5 * 60 * 1000,
  });
}

export function useSaldos() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["contas", "saldos"],
    queryFn: async () => {
      const result = await api.get("/api/contas/saldos");
      return result.data;
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useCreateConta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: Partial<Conta>) => {
      const result = await api.post("/api/contas", data);
      return result.data as Conta;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["contas"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["patrimonio"] });
      toast.success("Conta criada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao criar conta", { description: error.message });
    },
  });
}

export function useUpdateConta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: Partial<Conta> & { id: string }) => {
      const result = await api.patch(`/api/contas/${id}`, data);
      return result.data as Conta;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["contas"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["patrimonio"] });
      toast.success("Conta atualizada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao atualizar conta", { description: error.message });
    },
  });
}

export function useDeleteConta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/contas/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["contas"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["patrimonio"] });
      toast.success("Conta excluída com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao excluir conta", { description: error.message });
    },
  });
}
