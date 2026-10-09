/**
 * "A visita aconteceu?" hooks (CONTRACT sw-lead-to-contract §3.2–3.4):
 * the org-wide list of roteiros awaiting an answer, the answer itself, and the
 * visited-imóveis list that feeds "Gerar proposta".
 *
 * 🔴 `loading` here is never `isLoading`: consumers derive
 * `showSkeleton = isPending && !data` and `isRefreshing = isFetching && !!data`.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

import { roteirosKeys } from "@/hooks/useCardHub";
import { pessoaKey } from "@/hooks/usePessoa";
import type {
  Roteiro,
  RoteiroFeedbackBody,
  RoteiroPendenteFeedback,
  VisitadaItem,
} from "@/types/cardHub";

export const ROTEIROS_PENDENTES_KEY = ["sw", "roteiros", "pendentes-feedback"] as const;
const visitadasKey = (clienteId: string, roteiroId: string) =>
  [...roteirosKeys.family(clienteId), "visitadas", roteiroId] as const;

const base = (clienteId: string) => `/api/clientes/${encodeURIComponent(clienteId)}`;

export function useRoteirosPendentesFeedback() {
  return useQuery({
    queryKey: ROTEIROS_PENDENTES_KEY,
    queryFn: () => api.get<RoteiroPendenteFeedback[]>("/api/roteiros/pendentes-feedback"),
  });
}

export function useResponderFeedbackRoteiro(clienteId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ roteiroId, body }: { roteiroId: string; body: RoteiroFeedbackBody }) =>
      api.post<Roteiro>(
        `${base(clienteId)}/roteiros/${encodeURIComponent(roteiroId)}/feedback`,
        body,
      ),
    onSuccess: () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: roteirosKeys.family(clienteId) }),
        qc.invalidateQueries({ queryKey: ROTEIROS_PENDENTES_KEY }),
        qc.invalidateQueries({ queryKey: pessoaKey(clienteId) }),
        qc.invalidateQueries({ queryKey: ["sw", "metricas"] }),
      ]),
  });
}

export function useVisitadas(clienteId: string, roteiroId: string, enabled = true) {
  return useQuery({
    queryKey: visitadasKey(clienteId, roteiroId),
    queryFn: () =>
      api.get<VisitadaItem[]>(
        `${base(clienteId)}/roteiros/${encodeURIComponent(roteiroId)}/visitadas`,
      ),
    enabled,
  });
}
