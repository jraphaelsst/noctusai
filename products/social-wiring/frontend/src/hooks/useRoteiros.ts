/**
 * useCriarRoteiro — create a roteiro from ORDERED códigos + `data_visita`
 * (CONTRACT §5.1), then optionally fetch its PDF (§5.2).
 *
 * `useRoteiroMutations` (useCardHub) owns the cache invalidation (roteiros list
 * + timeline) and the POST; this hook composes it and adds the pessoa-payload
 * invalidation (`contagens.roteiros`).
 */
import { useQueryClient } from "@tanstack/react-query";

import { baixarRoteiroPdf, useRoteiroMutations } from "@/hooks/useCardHub";
import { pessoaKey } from "@/hooks/usePessoa";
import type { Roteiro, RoteiroCreateBody } from "@/types/cardHub";

export function useCriarRoteiro(clienteId: string) {
  const qc = useQueryClient();
  const { create } = useRoteiroMutations(clienteId);

  async function criar(body: RoteiroCreateBody): Promise<Roteiro> {
    const roteiro = await create.mutateAsync(body);
    void qc.invalidateQueries({ queryKey: pessoaKey(clienteId) });
    return roteiro;
  }

  return { criar, isPending: create.isPending };
}

export { baixarRoteiroPdf };
