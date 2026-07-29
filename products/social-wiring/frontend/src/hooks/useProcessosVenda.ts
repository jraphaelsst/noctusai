/**
 * Processos de Venda — data hooks.
 *
 * Lives here rather than inline in `pages/funil/ProcessosVenda.tsx` for the
 * same reason every other data hook in this product does: a page that declares
 * its own `useMutation` owns cache-invalidation logic that nothing else can
 * reuse or test in isolation, and the `find_inline_hooks` analyzer flags it.
 *
 * The board list itself comes from the seed pipeline seam
 * (`usePipelineSeam` / `processosPipeline`); only the archive mutation is
 * product-local, because archiving is not part of the shared board mechanic.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api } from "@/lib/api";

/** Query key the processos board reads under — exported so a caller
 *  invalidating from elsewhere cannot drift from this hook's key. */
export const PROCESSOS_QUERY_KEY = ["sw-processos"] as const;

export function useArquivarProcesso() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (processoId: string) => {
      const result: any = await api.post(
        `/api/processos-venda/${processoId}/arquivar`,
      );
      return result?.data ?? result;
    },
    onSuccess: (processo: any) => {
      toast.success(
        processo?.arquivado ? "Processo arquivado" : "Processo restaurado",
      );
    },
    onError: (error: Error) =>
      toast.error("Erro ao arquivar processo", { description: error.message }),
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: PROCESSOS_QUERY_KEY }),
  });
}
