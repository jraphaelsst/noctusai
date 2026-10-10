/**
 * Assuntos Virais — TanStack Query hooks over
 * `/api/media-creation/pesquisa/assuntos-virais` (contract
 * projects/core-studio/specs/pesquisa-wave2-contract.md §3 #18–26).
 *
 * Loading rule (lying-loading-state.md): query hooks return
 * `showSkeleton = isPending && !data` and `isRefreshing = isFetching && !!data`
 * with `placeholderData` on key changes — never `isLoading`. Every mutation
 * invalidates the whole `["sw","assuntos-virais"]` family (list + counts).
 */
import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

import type { FonteKind } from "@/hooks/usePesquisa";

export type AssuntoStatus = "pending" | "approved";
export type AssuntoSort = "plays" | "recent";

export interface ViralTopic {
  id: string;
  marca_id: string;
  topic: string;
  status: AssuntoStatus;
  origin: "manual" | "extraction";
  total_plays: number | null;
  fontes_count: number;
  created_at: string;
}

export interface ViralTopicSource {
  source_kind: FonteKind;
  account_id: string | null;
  source_id: string;
  url: string | null;
  thumbnail_url: string | null;
  published_at: string | null;
  plays: number | null;
  likes: number | null;
  comments: number | null;
  excerpt: string | null;
}

export interface AssuntosPage {
  items: ViralTopic[];
  total: number;
}

export interface AssuntosCounts {
  approved: number;
  pending: number;
}

export type AssuntoBulkAction = "approve" | "reject" | "delete";

export const ASSUNTOS_PAGE_SIZE = 54;

const BASE = "/api/media-creation/pesquisa/assuntos-virais";
export const ASSUNTOS_KEY = ["sw", "assuntos-virais"] as const;
const listKey = (
  marcaId: string | null,
  status: AssuntoStatus,
  sort: AssuntoSort,
) => [...ASSUNTOS_KEY, "list", marcaId, status, sort] as const;
const countsKey = (marcaId: string | null) =>
  [...ASSUNTOS_KEY, "counts", marcaId] as const;
const fontesKey = (id: string | null) =>
  [...ASSUNTOS_KEY, "fontes", id] as const;

interface Envelope<T> {
  success?: boolean;
  data: T;
}
const unwrap = <T>(res: Envelope<T>): T => res.data;

export function useAssuntosVirais(
  marcaId: string | null,
  status: AssuntoStatus,
  sort: AssuntoSort = "plays",
) {
  const query = useInfiniteQuery({
    queryKey: listKey(marcaId, status, sort),
    enabled: !!marcaId,
    initialPageParam: 0,
    queryFn: async ({ pageParam }) => {
      const params = new URLSearchParams({
        marca_id: marcaId as string,
        status,
        sort,
        limit: String(ASSUNTOS_PAGE_SIZE),
        offset: String(pageParam),
      });
      return unwrap(
        await api.get<Envelope<AssuntosPage>>(`${BASE}?${params.toString()}`),
      );
    },
    getNextPageParam: (last, all) => {
      const loaded = all.reduce((n, p) => n + p.items.length, 0);
      return loaded < last.total && last.items.length > 0 ? loaded : undefined;
    },
    placeholderData: keepPreviousData,
  });
  const items = query.data?.pages.flatMap((p) => p.items) ?? [];
  const total = query.data?.pages[query.data.pages.length - 1]?.total ?? 0;
  return {
    ...query,
    items,
    total,
    showSkeleton: !!marcaId && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data && !query.isFetchingNextPage,
  };
}

export function useAssuntosCounts(marcaId: string | null) {
  const query = useQuery({
    queryKey: countsKey(marcaId),
    enabled: !!marcaId,
    queryFn: async () =>
      unwrap(
        await api.get<Envelope<AssuntosCounts>>(
          `${BASE}/counts?marca_id=${encodeURIComponent(marcaId as string)}`,
        ),
      ),
    placeholderData: (prev) => prev,
  });
  return {
    ...query,
    showSkeleton: !!marcaId && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

export function useAssuntoFontes(assuntoId: string | null) {
  const query = useQuery({
    queryKey: fontesKey(assuntoId),
    enabled: !!assuntoId,
    queryFn: async () =>
      unwrap(
        await api.get<Envelope<ViralTopicSource[]>>(
          `${BASE}/${encodeURIComponent(assuntoId as string)}/fontes`,
        ),
      ) ?? [],
    placeholderData: (prev) => prev,
  });
  return {
    ...query,
    showSkeleton: !!assuntoId && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

function useInvalidateAssuntos() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ASSUNTOS_KEY });
}

export function useAdicionarAssuntos() {
  const invalidate = useInvalidateAssuntos();
  return useMutation({
    mutationFn: async (v: { marca_id: string; topics: string[] }) =>
      unwrap(
        await api.post<
          Envelope<{ saved: number; skipped: number; items: ViralTopic[] }>
        >(BASE, v),
      ),
    onSuccess: invalidate,
  });
}

export function useAprovarAssunto() {
  const invalidate = useInvalidateAssuntos();
  return useMutation({
    mutationFn: async (id: string) =>
      unwrap(
        await api.post<Envelope<ViralTopic>>(
          `${BASE}/${encodeURIComponent(id)}/approve`,
        ),
      ),
    onSuccess: invalidate,
  });
}

export function useRejeitarAssunto() {
  const invalidate = useInvalidateAssuntos();
  return useMutation({
    mutationFn: async (id: string) =>
      unwrap(
        await api.post<Envelope<ViralTopic>>(
          `${BASE}/${encodeURIComponent(id)}/reject`,
        ),
      ),
    onSuccess: invalidate,
  });
}

export function useExcluirAssunto() {
  const invalidate = useInvalidateAssuntos();
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`${BASE}/${encodeURIComponent(id)}`);
    },
    onSuccess: invalidate,
  });
}

export function useAssuntosEmMassa() {
  const invalidate = useInvalidateAssuntos();
  return useMutation({
    mutationFn: async (v: {
      marca_id: string;
      action: AssuntoBulkAction;
      ids: string[];
    }) =>
      unwrap(await api.post<Envelope<{ affected: number }>>(`${BASE}/bulk`, v)),
    onSuccess: invalidate,
  });
}

export function useEsvaziarAssuntos() {
  const invalidate = useInvalidateAssuntos();
  return useMutation({
    mutationFn: async (v: { marca_id: string; status: AssuntoStatus }) =>
      unwrap(
        await api.post<Envelope<{ deleted: number }>>(`${BASE}/empty`, {
          ...v,
          confirm: true,
        }),
      ),
    onSuccess: invalidate,
  });
}
