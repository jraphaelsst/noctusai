import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { toast } from "@/hooks/use-toast";

export function useCriarMetaHoje() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const result = await api.post("/api/metas/criar-hoje");
      return result.data as { message: string; metas_criadas: number };
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["metas"] });
      toast({
        title: "Sucesso!",
        description: data.message || "Metas de hoje criadas com sucesso.",
      });
    },
    onError: (error: Error) => {
      toast({
        title: "Erro",
        description: error.message || "Erro ao criar metas de hoje.",
        variant: "destructive",
      });
    },
  });
}
