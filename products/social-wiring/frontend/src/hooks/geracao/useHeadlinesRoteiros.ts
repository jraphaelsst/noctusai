/**
 * Headlines e Roteiros (estruturas-contract §6.8 / §6.9, FE-3): the combined list and the card's origin.
 * The page reuses the existing favoritar / editar / excluir / reprocessar mutations (their settle
 * invalidates the whole `["sw","geracao"]` family, which includes this list).
 *
 * Loading rule (lying-loading-state.md): `showSkeleton = isPending && !data`,
 * `isRefreshing = isFetching && !!data`, `placeholderData` keeps the previous page — never `isLoading`.
 * The list polls (3 s, background-safe) only while a visible roteiro is still being produced.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";
import { jobPolling } from "@noctusai/lib";

import { emAndamento } from "@/components/geracao/labels";
import { GERACAO_KEY } from "@/lib/geracaoKeys";
import { ESTEIRA_KEY } from "@/lib/esteiraKeys";
import type { EstruturaOrigemCard, HeadlineRoteiroItem } from "@/types/estruturas";

interface Envelope<T> {
  success?: boolean;
  data: T;
}
const unwrap = <T>(res: Envelope<T>): T => res.data;

const BASE = "/api/media-creation/headlines-roteiros";
export const HR_POLL_MS = 3000;
export const HR_PAGE_SIZE = 20;
export const HR_KEY = [...GERACAO_KEY, "headlines-roteiros"] as const;

export type RoteiroStatusFiltro = "criando" | "processando" | "completo" | "falha" | "sem_roteiro";
export type AprovacaoFiltro = "pendente" | "aprovado" | "rejeitado";

export interface HeadlinesRoteirosFiltros {
  marcaId: string | null;
  q?: string;
  estruturaId?: string | null;
  perfilId?: string | null;
  roteiroStatus?: RoteiroStatusFiltro | null;
  aprovacao?: AprovacaoFiltro | null;
  offset?: number;
}

export interface HeadlinesRoteirosPage {
  items: HeadlineRoteiroItem[];
  total: number;
}

export function headlinesRoteirosQuery(f: HeadlinesRoteirosFiltros): string {
  const p = new URLSearchParams({ marca_id: f.marcaId ?? "", limit: String(HR_PAGE_SIZE), offset: String(f.offset ?? 0) });
  if (f.q?.trim()) p.set("q", f.q.trim().slice(0, 200));
  if (f.estruturaId) p.set("estrutura_id", f.estruturaId);
  if (f.perfilId) p.set("perfil_id", f.perfilId);
  if (f.roteiroStatus) p.set("roteiro_status", f.roteiroStatus);
  if (f.aprovacao) p.set("aprovacao", f.aprovacao);
  return p.toString();
}

/** True while any visible roteiro is still being produced (drives the poll). */
export function algumRoteiroEmAndamento(items: HeadlineRoteiroItem[] | undefined): boolean {
  return !!items?.some((i) => !!i.roteiro && emAndamento(i.roteiro.status));
}

export function useHeadlinesRoteiros(f: HeadlinesRoteirosFiltros) {
  const query = useQuery({
    queryKey: [...HR_KEY, "lista", f],
    enabled: !!f.marcaId,
    queryFn: async () => unwrap(await api.get<Envelope<HeadlinesRoteirosPage>>(`${BASE}?${headlinesRoteirosQuery(f)}`)),
    ...jobPolling((d: HeadlinesRoteirosPage | undefined) => algumRoteiroEmAndamento(d?.items), HR_POLL_MS),
    placeholderData: keepPreviousData,
  });
  return {
    ...query,
    showSkeleton: !!f.marcaId && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

export const origemKey = (postId: string | null) => [...ESTEIRA_KEY, "origem", postId] as const;

/** `GET /esteira/posts/{id}/origem` — what the card came from (headline, roteiro, Estruturas, caption origin). */
export function useOrigemDoCard(postId: string | null, enabled = true) {
  const query = useQuery({
    queryKey: origemKey(postId),
    enabled: enabled && !!postId,
    queryFn: async () =>
      unwrap(await api.get<Envelope<EstruturaOrigemCard>>(`/api/media-creation/esteira/posts/${encodeURIComponent(postId as string)}/origem`)),
    placeholderData: (prev) => prev,
  });
  return {
    ...query,
    showSkeleton: enabled && !!postId && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}
