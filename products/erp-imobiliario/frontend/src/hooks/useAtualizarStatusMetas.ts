import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { toast } from "@/hooks/use-toast";

export function useAtualizarStatusMetas() {
  return useMutation({
    mutationFn: async () => {
      const result = await api.post("/api/metas/atualizar-status");
      return result.data as { metas_atualizadas: number };
    },
    onSuccess: (data) => {
      toast({
        title: "Status atualizado!",
        description: `${data.metas_atualizadas} metas foram atualizadas.`,
      });
    },
    onError: (error: Error) => {
      toast({
        title: "Erro",
        description: error.message || "Erro ao atualizar status das metas.",
        variant: "destructive",
      });
    },
  });
}
