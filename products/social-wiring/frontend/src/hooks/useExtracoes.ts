/**
 * Minhas extrações — TanStack Query hooks over `/api/media-creation/cerebro/extracoes`
 * (contract cerebro-contract.md §4 endpoints 19-24). v1 is pasted-text only (§10).
 *
 * Loading rule (lying-loading-state.md): `showSkeleton = isPending && !data`,
 * `isRefreshing = isFetching && !!data`, never `isLoading`. "Carregar mais" is offset
 * paging (`useInfiniteQuery`, fixed limit 20 <= server cap 100); previous rows stay
 * on screen on marca/search change via `placeholderData`. Mutations invalidate the whole `["sw","cerebro"]` family
 * (an apply changes brain content/size too).
 */
import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type InfiniteData,
} from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";
import { jobPolling } from "@noctusai/lib";
import { infiniteOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

import { CEREBRO_KEY, POLL_MS } from "@/hooks/useCerebro";
import type { ExtractionDetail, ExtractionSummary } from "@/types/cerebro";

const BASE = "/api/media-creation/cerebro/extracoes";
export const PAGE_SIZE = 20;

interface Envelope<T> {
  success?: boolean;
  data: T;
}
const unwrap = <T>(res: Envelope<T>): T => res.data;

export interface ExtracoesPage {
  items: ExtractionSummary[];
  total: number;
}

const listKey = (marcaId: string | null, q: string) =>
  [...CEREBRO_KEY, marcaId, "extracoes", { q }] as const;
const detailKey = (id: string | null) => [...CEREBRO_KEY, "extracao", id] as const;

export const extracaoEmAndamento = (e: { status: string } | undefined | null) => e?.status === "transcribing";

export function useExtracoes(marcaId: string | null, q: string) {
  const query = useInfiniteQuery({
    queryKey: listKey(marcaId, q),
    enabled: !!marcaId,
    initialPageParam: 0,
    queryFn: async ({ pageParam }) => {
      const p = new URLSearchParams({
        marca_id: marcaId as string,
        limit: String(PAGE_SIZE),
        offset: String(pageParam),
      });
      if (q.trim()) p.set("q", q.trim());
      return unwrap(await api.get<Envelope<ExtracoesPage>>(`${BASE}?${p.toString()}`));
    },
    // offset paging: next offset = rows loaded so far; stop once loaded >= total
    getNextPageParam: (last, all) => {
      const loaded = all.reduce((n, pg) => n + pg.items.length, 0);
      return last.items.length > 0 && loaded < last.total ? loaded : undefined;
    },
    select: (d): ExtracoesPage => ({
      items: d.pages.flatMap((pg) => pg.items),
      total: d.pages[d.pages.length - 1]?.total ?? 0,
    }),
    ...jobPolling(
      (d: InfiniteData<ExtracoesPage> | undefined) =>
        !!d?.pages.some((pg) => pg.items.some(extracaoEmAndamento)),
      POLL_MS,
    ),
    placeholderData: keepPreviousData,
  });
  return {
    ...query,
    showSkeleton: !!marcaId && query.isPending && !query.data,
    isRefreshing: query.isFetching && !query.isFetchingNextPage && !!query.data,
  };
}

export function useExtracao(id: string | null) {
  const query = useQuery({
    queryKey: detailKey(id),
    enabled: !!id,
    queryFn: async () =>
      unwrap(await api.get<Envelope<ExtractionDetail>>(`${BASE}/${encodeURIComponent(id as string)}`)),
    ...jobPolling((d: ExtractionDetail | undefined) => extracaoEmAndamento(d), POLL_MS),
    placeholderData: (prev) => (prev && prev.id === id ? prev : undefined),
  });
  return {
    ...query,
    showSkeleton: !!id && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

type ExtracoesCache = InfiniteData<ExtracoesPage>;
const EXTRACOES_FAMILY = [...CEREBRO_KEY] as const;

export function useCriarExtracao() {
  return useCacheWriteMutation<ExtractionDetail, { marca_id: string; name: string; brain_ids: string[]; text: string }>({
    mutationFn: async (v) => unwrap(await api.post<Envelope<ExtractionDetail>>(BASE, v)),
    // Newest first: the new extraction heads the marca's unfiltered list.
    targets: (v) => [
      {
        queryKey: listKey(v.marca_id, ""),
        commit: (old: ExtracoesCache | undefined, saved) => infiniteOps.prepend(old, saved),
      },
    ],
    invalidate: [CEREBRO_KEY],
  });
}

export function useAtualizarExtracao() {
  return useCacheWriteMutation<
    ExtractionDetail,
    { id: string; name?: string; transcript?: string; brain_ids?: string[] }
  >({
    mutationFn: async (v) => {
      const { id, ...body } = v;
      return unwrap(await api.patch<Envelope<ExtractionDetail>>(`${BASE}/${encodeURIComponent(id)}`, body));
    },
    targets: (v) => [
      { queryKey: detailKey(v.id), commit: (_old: ExtractionDetail | undefined, saved) => saved },
      {
        queryKey: EXTRACOES_FAMILY,
        match: "prefix",
        commit: (old: ExtracoesCache | undefined, saved) => infiniteOps.patch(old, v.id, saved),
      },
    ],
    invalidate: [CEREBRO_KEY],
  });
}

export function useAplicarExtracao() {
  const qc = useQueryClient();
  return useMutation({ // noc-allow: invalidate-only — applying writes to the brains (applied/skipped ids only in the answer): the affected brains come from a refetch
    mutationFn: async (v: { id: string; brain_ids?: string[] }) =>
      unwrap(
        await api.post<Envelope<{ applied: string[]; skipped: string[] }>>(
          `${BASE}/${encodeURIComponent(v.id)}/apply`,
          v.brain_ids ? { brain_ids: v.brain_ids } : {},
        ),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: CEREBRO_KEY }),
  });
}

export function useExcluirExtracao() {
  return useCacheWriteMutation<void, string>({
    mutationFn: async (id) => {
      await api.delete(`${BASE}/${encodeURIComponent(id)}`);
    },
    targets: (id) => [
      {
        queryKey: EXTRACOES_FAMILY,
        match: "prefix",
        optimistic: (old: ExtracoesCache | undefined) => infiniteOps.remove(old, id),
      },
    ],
    invalidate: [CEREBRO_KEY],
  });
}
