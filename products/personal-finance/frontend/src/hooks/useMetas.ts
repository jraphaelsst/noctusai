import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, useAuthStore } from '@noctusai/seed/infra';
import { toast } from "sonner";
import type { Meta } from "@/types";

export function useMetas(status?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["metas", status],
    queryFn: async () => {
      const params: Record<string, any> = {};
      if (status) params.status = status;
      const result = await api.get("/api/metas", params);
      return (result.data || []) as Meta[];
    },
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
  });
}

export function useMeta(id?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["meta", id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/metas/${id}`);
      return result.data as Meta;
    },
    enabled: !!user && !!id,
    staleTime: 5 * 60 * 1000,
  });
}

export function useMetaProgresso(id?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["meta", id, "progresso"],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/metas/${id}/progresso`);
      return result.data;
    },
    enabled: !!user && !!id,
    staleTime: 2 * 60 * 1000,
  });
}

export function useCreateMeta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: Partial<Meta>) => {
      const result = await api.post("/api/metas", data);
      return result.data as Meta;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["metas"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success("Meta criada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao criar meta", { description: error.message });
    },
  });
}

export function useUpdateMeta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: Partial<Meta> & { id: string }) => {
      const result = await api.patch(`/api/metas/${id}`, data);
      return result.data as Meta;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["metas"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success("Meta atualizada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao atualizar meta", { description: error.message });
    },
  });
}

export function useDeleteMeta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/metas/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["metas"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success("Meta excluida com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao excluir meta", { description: error.message });
    },
  });
}

export function useAddContribuicao() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: { id: string; valor: number; descricao?: string }) => {
      const result = await api.post(`/api/metas/${id}/contribuicao`, data);
      return result.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["metas"] });
      queryClient.invalidateQueries({ queryKey: ["meta"] });
      queryClient.invalidateQueries({ queryKey: ["contas"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success("Contribuicao adicionada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao adicionar contribuicao", { description: error.message });
    },
  });
}
