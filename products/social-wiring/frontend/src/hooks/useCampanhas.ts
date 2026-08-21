/**
 * Campanhas hooks — the "solicitar campanha" signal.
 *
 * Scope is deliberately the button and nothing else (user, 2026-08-20:
 * "keep it simple for later refinement"). Campaign CRUD proper is not here.
 *
 * The request is a SIGNAL, not a campaign: a corretor pressing it says
 * "this imóvel deserves paid traffic". Budget, channel and dates belong to
 * whoever decides them, which is not the person pressing the button.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

export interface Solicitacao {
  id?: string;
  imovel_ref_id?: string;
  status?: string;
  justificativa?: string | null;
  solicitado_em?: string;
}

const SOLICITACAO_KEY = (codigo: string) =>
  ["sw", "campanhas", "solicitacao", codigo] as const;

/**
 * The pending request for one imóvel, or null.
 *
 * The endpoint returns `{}` rather than 404 when there is none — "no
 * pending request" is the normal state of every imóvel, and a 404 would
 * make this state-check look like an error in the logs.
 */
export function useSolicitacaoDoImovel(codigo: string | null) {
  return useQuery({
    queryKey: SOLICITACAO_KEY(codigo ?? ""),
    queryFn: async () => {
      const res = await api.get<Solicitacao>(
        `/api/campanhas/solicitacoes/${codigo}`,
      );
      return res && res.id ? res : null;
    },
    enabled: Boolean(codigo),
  });
}

export function useSolicitarCampanha(codigo: string | null) {
  const qc = useQueryClient();
  return useMutation<Solicitacao, Error, string | undefined>({
    mutationFn: async (justificativa) =>
      api.post<Solicitacao>("/api/campanhas/solicitacoes", {
        codigo,
        justificativa: justificativa ?? null,
      }),
    onSuccess: () => {
      // The button's own state is derived from the pending query, so it
      // has to re-read before the UI can stop offering the action.
      qc.invalidateQueries({ queryKey: SOLICITACAO_KEY(codigo ?? "") });
      qc.invalidateQueries({ queryKey: ["sw", "campanhas", "solicitacoes"] });
    },
  });
}
