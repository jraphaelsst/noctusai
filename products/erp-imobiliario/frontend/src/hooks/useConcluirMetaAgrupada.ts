import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from '@noctusai/seed/infra';
import { toast } from "sonner";
import { METAS_ROOT } from "./useMetas";

export function useConcluirMetaAgrupada() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (metaId: string) => {
      const result = await api.post(`/api/metas/${metaId}/concluir`);
      return result.data as { success: boolean; error?: string; message?: string };
    },
    onSuccess: (data) => {
      // `concluir_meta_agrupada` (migrations/003) only writes `erp.metas` —
      // no meta_evento row, so the team/gamification domain
      // (useMetasDomain.ts) is untouched; scoped to METAS_ROOT.
      queryClient.invalidateQueries({ queryKey: [METAS_ROOT] });
      toast.success("Sucesso!", { description: data.message || "Meta concluída com sucesso." });
    },
    onError: (error: Error) => {
      toast.error("Erro", { description: error.message || "Erro ao concluir meta." });
    },
  });
}
