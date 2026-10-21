/**
 * Assuntos Virais — TanStack Query hooks over
 * `/api/media-creation/pesquisa/assuntos-virais` (contract
 * projects/core-studio-build/specs/pesquisa-wave2-contract.md §3 #18–26).
 *
 * Loading rule (lying-loading-state.md): query hooks return
 * `showSkeleton = isPending && !data` and `isRefreshing = isFetching && !!data`
 * with `placeholderData` on key changes — never `isLoading`. Every mutation
 * writes the answer into the cached lists it affects (rows leave the lists they no longer belong to) and
 * invalidates the whole `["sw","assuntos-virais"]` family (list + counts) in the background.
 */
import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryKey,
} from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";
import { infiniteOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

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

type AssuntosCache = { pages: AssuntosPage[]; pageParams: unknown[] };

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

/** Every cached list of every marca/status/sort: `[…ASSUNTOS_KEY, "list", marcaId, status, sort]`. */
const LISTAS_KEY = [...ASSUNTOS_KEY, "list"] as const;
const statusDaLista = (key?: QueryKey) => key?.[4];

export function useAdicionarAssuntos() {
  const invalidate = useInvalidateAssuntos();
  return useMutation({ // noc-allow: invalidate-only — lists are sorted by plays/recency server-side and the server dedupes (skipped): where (and whether) each new topic lands in each cached sort is its call
    mutationFn: async (v: { marca_id: string; topics: string[] }) =>
      unwrap(
        await api.post<
          Envelope<{ saved: number; skipped: number; items: ViralTopic[] }>
        >(BASE, v),
      ),
    onSuccess: invalidate,
  });
}

/** Approve: the row leaves the pending lists at once; the approved lists place it (sorted server-side) on the settle. */
export function useAprovarAssunto() {
  return useCacheWriteMutation<ViralTopic, string>({
    mutationFn: async (id) =>
      unwrap(
        await api.post<Envelope<ViralTopic>>(
          `${BASE}/${encodeURIComponent(id)}/approve`,
        ),
      ),
    targets: (id) => [
      {
        queryKey: LISTAS_KEY,
        match: "prefix",
        optimistic: (old: AssuntosCache | undefined, _id, _ctx, key) =>
          statusDaLista(key) === "pending" ? infiniteOps.remove(old, id) : old,
        commit: (old: AssuntosCache | undefined, saved, _id, _ctx, key) =>
          statusDaLista(key) === saved.status ? infiniteOps.replace(old, id, saved) : infiniteOps.remove(old, id),
      },
    ],
    invalidate: [ASSUNTOS_KEY],
  });
}

/** Reject: the row belongs to neither the pending nor the approved list any more. */
export function useRejeitarAssunto() {
  return useCacheWriteMutation<ViralTopic, string>({
    mutationFn: async (id) =>
      unwrap(
        await api.post<Envelope<ViralTopic>>(
          `${BASE}/${encodeURIComponent(id)}/reject`,
        ),
      ),
    targets: (id) => [
      {
        queryKey: LISTAS_KEY,
        match: "prefix",
        commit: (old: AssuntosCache | undefined, saved, _id, _ctx, key) =>
          statusDaLista(key) === saved.status ? infiniteOps.replace(old, id, saved) : infiniteOps.remove(old, id),
      },
    ],
    invalidate: [ASSUNTOS_KEY],
  });
}

export function useExcluirAssunto() {
  return useCacheWriteMutation<void, string>({
    mutationFn: async (id) => {
      await api.delete(`${BASE}/${encodeURIComponent(id)}`);
    },
    targets: (id) => [
      {
        queryKey: LISTAS_KEY,
        match: "prefix",
        optimistic: (old: AssuntosCache | undefined) => infiniteOps.remove(old, id),
      },
    ],
    invalidate: [ASSUNTOS_KEY],
  });
}

/** Bulk: approve takes the ids off the pending lists; reject / delete take them off every list. */
export function useAssuntosEmMassa() {
  return useCacheWriteMutation<
    { affected: number },
    { marca_id: string; action: AssuntoBulkAction; ids: string[] }
  >({
    mutationFn: async (v) =>
      unwrap(await api.post<Envelope<{ affected: number }>>(`${BASE}/bulk`, v)),
    targets: (v) => [
      {
        queryKey: LISTAS_KEY,
        match: "prefix",
        optimistic: (old: AssuntosCache | undefined, _vars, _ctx, key) =>
          v.action === "approve" && statusDaLista(key) !== "pending"
            ? old
            : v.ids.reduce<AssuntosCache | undefined>((acc, id) => infiniteOps.remove(acc, id), old),
      },
    ],
    invalidate: [ASSUNTOS_KEY],
  });
}

/** Empty a status list: that marca's lists of that status (every sort) go blank at once. */
export function useEsvaziarAssuntos() {
  return useCacheWriteMutation<{ deleted: number }, { marca_id: string; status: AssuntoStatus }>({
    mutationFn: async (v) =>
      unwrap(
        await api.post<Envelope<{ deleted: number }>>(`${BASE}/empty`, {
          ...v,
          confirm: true,
        }),
      ),
    targets: (v) => [
      {
        queryKey: LISTAS_KEY,
        match: "prefix",
        predicate: (key) => key[3] === v.marca_id && statusDaLista(key) === v.status,
        optimistic: (old: AssuntosCache | undefined) =>
          infiniteOps.mapPages(old, (pg) => ({ ...(pg as AssuntosPage), items: [], total: 0 })),
      },
    ],
    invalidate: [ASSUNTOS_KEY],
  });
}
