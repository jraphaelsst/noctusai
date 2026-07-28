/**
 * The seam between the two boards, as a proper mutation.
 *
 * `createPipelineHooks` covers everything a board does to ITSELF (query, move,
 * archive, stage CRUD). Accepting a proposal is the one action that spans both
 * boards — it closes a negociação here and opens a processo there — so it
 * lives with the product, not in the seed primitive.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api } from "@/lib/api";
import type { NegociacaoVenda, ProcessoVenda } from "@/types/pipeline";

interface AceitarPropostaResult {
  negociacao: NegociacaoVenda;
  processo: ProcessoVenda;
  /** True when the deal was already in execution — a repeat click, not an error. */
  already_accepted: boolean;
}

export function useAceitarProposta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (negociacaoId: string) => {
      const result: any = await api.post(
        `/api/negociacoes-venda/${negociacaoId}/aceitar-proposta`,
      );
      return (result?.data ?? result) as AceitarPropostaResult;
    },
    onSuccess: (data) => {
      if (data?.already_accepted) {
        toast.info("Esta proposta já havia sido aceita", {
          description: "O processo de venda já existe.",
        });
      } else {
        toast.success("Proposta aceita", {
          description: "A negociação foi movida para Processos de Venda.",
        });
      }
    },
    onError: (error: Error) => {
      toast.error("Erro ao aceitar proposta", { description: error.message });
    },
    onSettled: () => {
      // BOTH boards changed: the card left this one and appeared on the other.
      // Invalidating only the Funil would leave Processos showing a stale board
      // until something else happened to refetch it.
      queryClient.invalidateQueries({ queryKey: ["sw-funil"] });
      queryClient.invalidateQueries({ queryKey: ["sw-processos"] });
      queryClient.invalidateQueries({ queryKey: ["negociacoes-venda"] });
    },
  });
}
