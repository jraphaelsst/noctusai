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
import { useQuery } from "@tanstack/react-query";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";
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
  return useCacheWriteMutation<Solicitacao, string | undefined>({
    mutationFn: async (justificativa) =>
      api.post<Solicitacao>("/api/campanhas/solicitacoes", {
        codigo,
        justificativa: justificativa ?? null,
      }),
    // The button's own state is derived from the pending query: the saved request IS that state.
    targets: [
      {
        queryKey: SOLICITACAO_KEY(codigo ?? ""),
        commit: (_old, saved) => (saved && saved.id ? saved : undefined),
      },
    ],
    invalidate: [["sw", "campanhas", "solicitacoes"]],
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
  const criar = useCacheWriteMutation<Campanha, CampanhaBody>({
    mutationFn: async (body) => (await api.post<{ data: Campanha }>("/api/campanhas", body)).data,
    targets: [{ queryKey: CAMPANHAS_KEY, commit: (old, saved) => listOps.replace(old, saved.id, saved) }],
  });
  const atualizar = useCacheWriteMutation<Campanha, { id: string; body: CampanhaBody }>({
    mutationFn: async ({ id, body }) =>
      (await api.patch<{ data: Campanha }>(`/api/campanhas/${encodeURIComponent(id)}`, body)).data,
    targets: ({ id }) => [{ queryKey: CAMPANHAS_KEY, commit: (old, saved) => listOps.replace(old, id, saved) }],
  });
  const remover = useCacheWriteMutation<unknown, { id: string }>({
    mutationFn: ({ id }) => api.delete(`/api/campanhas/${encodeURIComponent(id)}`),
    targets: ({ id }) => [{ queryKey: CAMPANHAS_KEY, optimistic: (old) => listOps.remove(old, id) }],
  });
  return { criar, atualizar, remover };
}
