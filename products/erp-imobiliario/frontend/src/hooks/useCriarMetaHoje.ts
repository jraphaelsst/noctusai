import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from '@noctusai/seed/infra';
import { toast } from "sonner";
import { METAS_ROOT } from "./useMetas";

export function useCriarMetaHoje() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const result = await api.post("/api/metas/criar-hoje");
      return result.data as { message: string; metas_criadas: number };
    },
    onSuccess: (data) => {
      // Scaffolds today's personal metas from the corretor's active configs —
      // never touches the team/gamification "metas" domain (see useMetas.ts
      // METAS_ROOT docblock), so scoped to METAS_ROOT only.
      queryClient.invalidateQueries({ queryKey: [METAS_ROOT] });
      toast.success("Sucesso!", { description: data.message || "Metas de hoje criadas com sucesso." });
    },
    onError: (error: Error) => {
      toast.error("Erro", { description: error.message || "Erro ao criar metas de hoje." });
    },
  });
}
