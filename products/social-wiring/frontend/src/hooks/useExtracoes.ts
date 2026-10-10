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
import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

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
    refetchInterval: (s) =>
      s.state.data?.pages.some((pg) => pg.items.some(extracaoEmAndamento)) ? POLL_MS : false,
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
    refetchInterval: (s) => (extracaoEmAndamento(s.state.data) ? POLL_MS : false),
    placeholderData: (prev) => (prev && prev.id === id ? prev : undefined),
  });
  return {
    ...query,
    showSkeleton: !!id && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

function useInvalidateCerebro() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: CEREBRO_KEY });
}

export function useCriarExtracao() {
  const invalidate = useInvalidateCerebro();
  return useMutation({
    mutationFn: async (v: { marca_id: string; name: string; brain_ids: string[]; text: string }) =>
      unwrap(await api.post<Envelope<ExtractionDetail>>(BASE, v)),
    onSuccess: invalidate,
  });
}

export function useAtualizarExtracao() {
  const invalidate = useInvalidateCerebro();
  return useMutation({
    mutationFn: async (v: { id: string; name?: string; transcript?: string; brain_ids?: string[] }) => {
      const { id, ...body } = v;
      return unwrap(await api.patch<Envelope<ExtractionDetail>>(`${BASE}/${encodeURIComponent(id)}`, body));
    },
    onSuccess: invalidate,
  });
}

export function useAplicarExtracao() {
  const invalidate = useInvalidateCerebro();
  return useMutation({
    mutationFn: async (v: { id: string; brain_ids?: string[] }) =>
      unwrap(
        await api.post<Envelope<{ applied: string[]; skipped: string[] }>>(
          `${BASE}/${encodeURIComponent(v.id)}/apply`,
          v.brain_ids ? { brain_ids: v.brain_ids } : {},
        ),
      ),
    onSuccess: invalidate,
  });
}

export function useExcluirExtracao() {
  const invalidate = useInvalidateCerebro();
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`${BASE}/${encodeURIComponent(id)}`);
    },
    onSuccess: invalidate,
  });
}
