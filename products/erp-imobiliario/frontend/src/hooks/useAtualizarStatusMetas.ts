import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { toast } from "sonner";

export function useAtualizarStatusMetas() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const result = await api.post("/api/metas/atualizar-status");
      return result.data as { metas_atualizadas: number };
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["metas"] });
      toast.success("Status atualizado!", { description: `${data.metas_atualizadas} metas foram atualizadas.` });
    },
    onError: (error: Error) => {
      toast.error("Erro", { description: error.message || "Erro ao atualizar status das metas." });
    },
  });
}
