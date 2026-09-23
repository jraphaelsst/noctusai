import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, useAuthStore } from '@noctusai/seed/infra';
import { Meta, NovaMetaForm } from "@/types";
import { toast } from "sonner";
import { getDisplayCategoria } from "@/lib/categorias";

/**
 * Root key for the PERSONAL goal tracker (`/api/metas` — a corretor's own
 * "diaria/semanal/mensal/anual" targets). Deliberately namespaced away from
 * `useMetasDomain.ts`'s `["metas", ...]` keys (equipes, periodos, empresa,
 * regras, config, rankings, fechamentos — the team/gamification cascade):
 * those two backends share nothing (confirmed against
 * `backend/app/routers/metas.py` vs `metas_equipe.py`/`metas_empresa.py`;
 * `meta_eventos.referencia_tipo` is `ativo|evento|comissoes_split|contrato`,
 * never "meta"), yet every mutation here used to `invalidateQueries({
 * queryKey: ["metas"] })`, which TanStack prefix-matches against BOTH
 * domains. `MetasDashboard.tsx` renders both side by side, so clicking
 * "atualizar status" on a personal meta was silently re-fetching equipes,
 * periodos, rankings and config too. Renaming the root removes the
 * collision instead of trying to guess a narrower shared prefix.
 */
export const METAS_ROOT = "metas-pessoais";

export function useMetas(corretorId?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: [METAS_ROOT, corretorId],
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
      queryClient.invalidateQueries({ queryKey: [METAS_ROOT] });
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
      queryClient.invalidateQueries({ queryKey: [METAS_ROOT] });
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
      queryClient.invalidateQueries({ queryKey: [METAS_ROOT] });
      toast.success("Meta excluída!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao excluir meta", { description: error.message });
    },
  });
}
