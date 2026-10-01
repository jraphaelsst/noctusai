/**
 * useCriarRoteiro — create a roteiro from ORDERED códigos + `data_visita`
 * (CONTRACT §5.1), then optionally fetch its PDF (§5.2).
 *
 * `useCardHub.ts` is frozen for this project, and its `useRoteiroMutations`
 * already owns the cache invalidation (roteiros list + timeline). This hook
 * composes it (the body type is a SUBTYPE of its `RoteiroCreateBody`, so
 * `data_visita` rides through to the POST) and adds the pessoa-payload
 * invalidation (`contagens.roteiros`).
 */
import { useQueryClient } from "@tanstack/react-query";

import { baixarRoteiroPdf, useRoteiroMutations } from "@/hooks/useCardHub";
import { pessoaKey } from "@/hooks/usePessoa";
import type { Roteiro } from "@/types/cardHub";
import type { RoteiroCriarBody } from "@/types/roteiros";

export function useCriarRoteiro(clienteId: string) {
  const qc = useQueryClient();
  const { create } = useRoteiroMutations(clienteId);

  async function criar(body: RoteiroCriarBody): Promise<Roteiro> {
    const roteiro = await create.mutateAsync(body);
    void qc.invalidateQueries({ queryKey: pessoaKey(clienteId) });
    return roteiro;
  }

  return { criar, isPending: create.isPending };
}

export { baixarRoteiroPdf };
