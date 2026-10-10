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

// ─── Campanhas CRUD (CONTRACT §1.1) ─────────────────────────────────────────
//
// A campanha maps Meta objects (campaign / adset / ad / form) to imóveis, so a
// lead arriving from one of them resolves its imóvel at intake.

export type VeiculacaoNivel = "campaign" | "adset" | "ad" | "form";

export interface CampanhaImovel {
  codigo: string;
  titulo: string | null;
}

export interface CampanhaVeiculacao {
  id: string;
  canal: "meta_ads";
  nivel: VeiculacaoNivel;
  ref_codigo: string;
}

export interface Campanha {
  id: string;
  nome: string;
  imoveis: CampanhaImovel[];
  veiculacoes: CampanhaVeiculacao[];
  created_at: string;
}

export interface CampanhaBody {
  nome: string;
  imovel_codigos: string[];
  veiculacoes: { canal: "meta_ads"; nivel: VeiculacaoNivel; ref_codigo: string }[];
}

const CAMPANHAS_KEY = ["sw", "campanhas", "lista"] as const;

export function useCampanhasLista() {
  const query = useQuery({
    queryKey: CAMPANHAS_KEY,
    queryFn: async () => {
      const res = await api.get<{ data: Campanha[] }>("/api/campanhas");
      return res?.data ?? [];
    },
    placeholderData: (prev) => prev,
  });
  return {
    ...query,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

export function useCampanhaMutations() {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: CAMPANHAS_KEY });
  const criar = useMutation({
    mutationFn: async (body: CampanhaBody) =>
      (await api.post<{ data: Campanha }>("/api/campanhas", body)).data,
    onSuccess: invalidate,
  });
  const atualizar = useMutation({
    mutationFn: async ({ id, body }: { id: string; body: CampanhaBody }) =>
      (await api.patch<{ data: Campanha }>(`/api/campanhas/${encodeURIComponent(id)}`, body)).data,
    onSuccess: invalidate,
  });
  const remover = useMutation({
    mutationFn: ({ id }: { id: string }) =>
      api.delete(`/api/campanhas/${encodeURIComponent(id)}`),
    onSuccess: invalidate,
  });
  return { criar, atualizar, remover };
}
