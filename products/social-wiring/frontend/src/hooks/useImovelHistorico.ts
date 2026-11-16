/**
 * Imóvel history — "Histórico" card data (owner 2026-11-04: every change to an imóvel is in its history).
 *
 *   GET  /api/imoveis/{codigo}/historico?cursor=&limit= → {data:{items:[{id,kind,ocorrido_em,ator,payload}], next_cursor}}
 *   POST /api/imoveis/{codigo}/divergencias/{id}/resolver {escolha: aprovar|recusar} (org admin) → Divergencia
 *
 * kinds: vista | aprovacao | vista_envio | alteracao | preco | nota. A pending approval is an `aprovacao` row with
 * `payload.status === "pendente"` and `payload.divergencia_id`.
 */
import { useInfiniteQuery } from "@tanstack/react-query";
import { infiniteOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { api } from "@noctusai/seed/infra";

export interface HistoricoPayload {
  campo?: string | null;
  rotulo?: string | null;
  de?: unknown;
  para?: unknown;
  acao?: string;
  conversa?: { id?: string | null; url?: string | null } | null;
  status?: "pendente" | "aprovada" | "recusada";
  divergencia_id?: string | null;
  detalhe?: string | null;
  // nota
  corpo?: string;
}

export interface HistoricoItem {
  id: string;
  kind: string;
  ocorrido_em: string;
  ator: { tipo: string; nome: string | null } | null;
  payload: HistoricoPayload;
}

interface HistoricoPagina {
  items: HistoricoItem[];
  next_cursor: string | null;
}

export type EscolhaAprovacao = "aprovar" | "recusar";

const KEY = (codigo: string) => ["sw", "imovel-dados", codigo, "historico"] as const;
const base = (codigo: string) => `/api/imoveis/${encodeURIComponent(codigo)}`;
const LIMITE = 30;

export function useImovelHistorico(codigo: string | null) {
  const query = useInfiniteQuery({
    queryKey: KEY(codigo ?? "__none__"),
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) => {
      const qs = new URLSearchParams({ limit: String(LIMITE) });
      if (pageParam) qs.set("cursor", pageParam);
      const res = await api.get<{ data: HistoricoPagina }>(`${base(codigo as string)}/historico?${qs}`);
      return { items: res?.data?.items ?? [], next_cursor: res?.data?.next_cursor ?? null } as HistoricoPagina;
    },
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: !!codigo,
    placeholderData: (prev) => prev,
  });
  const items = (query.data?.pages ?? []).flatMap((p) => p.items);
  return {
    ...query,
    items,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data && !query.isFetchingNextPage,
  };
}

export function useResolverAprovacao(codigo: string) {
  return useCacheWriteMutation<unknown, { historicoId: string; divergenciaId: string; escolha: EscolhaAprovacao }>({
    mutationFn: ({ divergenciaId, escolha }) =>
      api.post(`${base(codigo)}/divergencias/${encodeURIComponent(divergenciaId)}/resolver`, { escolha }),
    targets: [
      {
        queryKey: KEY(codigo),
        // The pending row leaves "pendente" on the click; the settle refetch brings the decision row the server wrote.
        optimistic: (old, { historicoId, escolha }) =>
          infiniteOps.mapPages(old as never, (p) => {
            const pagina = p as HistoricoPagina;
            if (!pagina.items?.some((i) => i.id === historicoId)) return p;
            return {
              ...pagina,
              items: pagina.items.map((i) =>
                i.id === historicoId
                  ? { ...i, payload: { ...i.payload, status: escolha === "aprovar" ? "aprovada" : "recusada" } }
                  : i,
              ),
            };
          }),
      },
    ],
    // Approving can change what the page shows (Vista value / our value).
    invalidate: [["sw", "imovel-dados", codigo], ["sw", "imoveis", "detail", codigo]],
  });
}
