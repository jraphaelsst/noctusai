import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { Meta, NovaMetaForm } from "@/types";
import { toast } from "sonner";
import { getDisplayCategoria } from "@/lib/categorias";
import { useAuthStore } from "@/store/authStore";

export function useMetas(corretorId?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["metas", corretorId],
    queryFn: async () => {
      const result = await api.get("/api/metas", {
        corretor_id: corretorId,
      });
      return (result.data || []) as Meta[];
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useCreateMeta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (novaMeta: NovaMetaForm) => {
      const result = await api.post("/api/metas", novaMeta);
      return result.data as Meta;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["metas"] });
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
    mutationFn: async ({ id, ...updates }: Partial<Meta> & { id: string }) => {
      const result = await api.patch(`/api/metas/${id}`, updates);
      return result.data as Meta;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["metas"] });
      toast.success("Meta atualizada!");
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
      toast.success("Meta excluída!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao excluir meta", { description: error.message });
    },
  });
}
