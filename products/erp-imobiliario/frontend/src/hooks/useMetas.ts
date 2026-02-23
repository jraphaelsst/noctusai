import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { Meta, NovaMetaForm } from "@/types";
import { toast } from "@/hooks/use-toast";
import { getDisplayCategoria } from "@/lib/categorias";

export function useMetas(corretorId?: string) {
  return useQuery({
    queryKey: ["metas", corretorId],
    queryFn: async () => {
      const result = await api.get("/api/metas", {
        corretor_id: corretorId,
      });
      return (result.data || []) as Meta[];
    },
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
      toast({ title: "Meta criada com sucesso!" });
    },
    onError: (error: any) => {
      toast({ title: "Erro ao criar meta", description: error.message, variant: "destructive" });
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
      toast({ title: "Meta atualizada!" });
    },
    onError: (error: any) => {
      toast({ title: "Erro ao atualizar meta", description: error.message, variant: "destructive" });
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
      toast({ title: "Meta excluída!" });
    },
    onError: (error: any) => {
      toast({ title: "Erro ao excluir meta", description: error.message, variant: "destructive" });
    },
  });
}
