/**
 * Atendimentos (Funil) — data hooks.
 *
 * Sibling of `useProcessosVenda.ts`'s `useArquivarProcesso`: archiving a
 * funil card is not part of the shared pipeline mechanic
 * (`createPipelineHooks` / `@noctusai/lib`'s `PipelineBoard`), so it lives
 * here as a product-local mutation, same reasoning that file's own header
 * gives.
 *
 * Unlike Processos' `/arquivar` TOGGLE endpoint, the funil card's archive
 * goes through the EXISTING `PATCH /api/atendimentos-venda/{id}`
 * (`AtendimentoUpdate.arquivado`, `boards.py`) — no new backend route:
 * setting `arquivado=true` is enough (the funil board already excludes
 * archived rows), and there is no restore affordance on this board (the
 * card owner's cliente stays active either way).
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { boardOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { FUNIL_PIPELINE_KEY } from "@/lib/funilKeys";
import type { MotivoPerdaCategoria } from "@/lib/motivoPerda";

/** The funil board cache is the bare `colunas` array ({cards, total}); a card that leaves the board is predictable. */
const funil = boardOps<{ id: string }>(() => 0);

const FUNIL_BOARD = (id: string) => ({
  queryKey: [FUNIL_PIPELINE_KEY],
  match: "prefix" as const,
  optimistic: (old: unknown) => funil.removeCard(old, id),
});

export function useArquivarAtendimento() {
  return useCacheWriteMutation<unknown, string>({
    mutationFn: async (atendimentoId) => {
      const result: any = await api.patch(
        `/api/atendimentos-venda/${atendimentoId}`,
        { arquivado: true },
      );
      return result?.data ?? result;
    },
    onSuccess: () => {
      toast.success("Card arquivado no funil");
    },
    onError: (error: Error) =>
      toast.error("Erro ao arquivar card", { description: error.message }),
    targets: (atendimentoId) => [FUNIL_BOARD(atendimentoId)],
    invalidate: [["atendimentos-venda"]],
  });
}

/**
 * Mark a funil card as LOST (`POST /api/atendimentos-venda/{id}/perder`).
 * `categoria` is the closed-set reason (the price evaluator aggregates it);
 * `motivo` is the operator's free note, required by the server for `outro`.
 *
 * Invalidates the funil board, the atendimentos family AND the card-hub cache
 * (`["sw","cardHub"]`) — the open card embeds the atendimento's status.
 */
export interface PerderAtendimentoInput {
  atendimentoId: string;
  categoria: MotivoPerdaCategoria;
  motivo?: string;
}

export function usePerderAtendimento() {
  const queryClient = useQueryClient();
  return useMutation({ // noc-allow: invalidate-only — where a lost card lands (stage/status) is decided by the server, so the board is regrouped there
    mutationFn: async ({ atendimentoId, categoria, motivo }: PerderAtendimentoInput) => {
      const nota = motivo?.trim();
      const result: any = await api.post(
        `/api/atendimentos-venda/${atendimentoId}/perder`,
        nota ? { categoria, motivo: nota } : { categoria },
      );
      return result?.data ?? result;
    },
    onSuccess: () => {
      toast.success("Card marcado como perdido");
    },
    onError: (error: Error) =>
      toast.error("Erro ao marcar card como perdido", { description: error.message }),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["sw-funil"] });
      queryClient.invalidateQueries({ queryKey: ["atendimentos-venda"] });
      queryClient.invalidateQueries({ queryKey: ["sw", "cardHub"] });
    },
  });
}
