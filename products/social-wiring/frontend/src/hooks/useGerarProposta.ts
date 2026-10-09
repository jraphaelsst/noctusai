/**
 * "Gerar proposta" from a visited imóvel — `POST /api/clientes/{id}/propostas
 * {visita_id}` (CONTRACT §4.2, built by the proposta slice).
 *
 * Kept as its own small hook so the roteiro tab does not import the proposta
 * module. A `409 visita_nao_realizada` surfaces as the mutation error.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

import { roteirosKeys } from "@/hooks/useCardHub";
import { pessoaKey } from "@/hooks/usePessoa";

export interface PropostaCriada {
  id: string;
  status: string;
}

export function useGerarProposta(clienteId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (visitaId: string) =>
      api.post<PropostaCriada>(`/api/clientes/${encodeURIComponent(clienteId)}/propostas`, {
        visita_id: visitaId,
      }),
    // The card's Geral tab (propostas), the visited list, the funnel stage and
    // the metrics all move when a proposta is created.
    onSuccess: () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: roteirosKeys.family(clienteId) }),
        qc.invalidateQueries({ queryKey: pessoaKey(clienteId) }),
        qc.invalidateQueries({ queryKey: ["sw", "metricas"] }),
        qc.invalidateQueries({ queryKey: ["sw", "propostas"] }),
      ]),
  });
}
