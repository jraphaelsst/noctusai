import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from '@noctusai/seed/infra';
import { toast } from "sonner";
import { METAS_ROOT } from "./useMetas";

export function useAtualizarStatusMetas() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const result = await api.post("/api/metas/atualizar-status");
      return result.data as { metas_atualizadas: number };
    },
    onSuccess: (data) => {
      // `erp.atualizar_status_metas()` (migrations/003) only UPDATEs
      // `erp.metas` (dias_restantes / status recompute) — never
      // `metas_config` (that's the separate `desativar_metas_usuarios_
      // inativos()` RPC) nor any team/gamification table, so scoped to
      // METAS_ROOT. This mutation is called side-by-side with
      // useMetasDomain's rankings/equipes/periodos on MetasDashboard.tsx —
      // it used to force-refetch all of them via the shared "metas" prefix.
      queryClient.invalidateQueries({ queryKey: [METAS_ROOT] });
      toast.success("Status atualizado!", { description: `${data.metas_atualizadas} metas foram atualizadas.` });
    },
    onError: (error: Error) => {
      toast.error("Erro", { description: error.message || "Erro ao atualizar status das metas." });
    },
  });
}
