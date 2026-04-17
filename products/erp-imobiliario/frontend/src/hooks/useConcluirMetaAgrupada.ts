import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from '@noctusai/seed/infra';
import { toast } from "sonner";

export function useConcluirMetaAgrupada() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (metaId: string) => {
      const result = await api.post(`/api/metas/${metaId}/concluir`);
      return result.data as { success: boolean; error?: string; message?: string };
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["metas"] });
      toast.success("Sucesso!", { description: data.message || "Meta concluída com sucesso." });
    },
    onError: (error: Error) => {
      toast.error("Erro", { description: error.message || "Erro ao concluir meta." });
    },
  });
}
