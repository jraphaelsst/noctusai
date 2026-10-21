/**
 * Minha Pesquisa — TanStack Query hooks over `/api/media-creation/pesquisa`
 * (build contract: projects/core-studio-build/specs/pesquisa-contract.md §3).
 *
 * Responses arrive wrapped in `success_response` ({success, data}); we unwrap
 * at the boundary. Loading rule (lying-loading-state.md): every query hook
 * returns `showSkeleton = isPending && !data` and `isRefreshing = isFetching
 * && !!data`, with `placeholderData` on key changes — never `isLoading`.
 * Every mutation writes what it knows into the cached lists (rows leave the
 * lists they no longer belong to) and invalidates the whole `["sw","pesquisa"]`
 * family (list + counts) in the background, so the page never shows stale numbers.
 */
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  keepPreviousData,
  type QueryKey,
} from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";
import { infiniteOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

// ─── Types (contract §3) ────────────────────────────────────────────────────

export type PesquisaGrupo = "publico" | "especialista" | "produto" | "global";
export type PesquisaStatus = "pending" | "approved";
export type PesquisaOrigem = "manual" | "ai_classified" | "extraction";
export type PesquisaSort = "recent" | "plays";

export interface PesquisaVariable {
  slug: string;
  label: string;
  grupo: PesquisaGrupo;
  description: string;
  classifiable: boolean;
  sort_order: number;
}

export type FonteKind = "instagram_media" | "youtube_video" | "mc_post";

/** Provenance of an extraction-origin item (contract wave2 §3.1). */
export interface SourceRef {
  kind: FonteKind;
  account_id: string | null;
  id: string;
  url: string | null;
  thumbnail_url: string | null;
  published_at: string | null;
  plays: number | null;
  likes: number | null;
  comments: number | null;
  excerpt: string | null;
  extracao_id: string | null;
}

export interface PesquisaItem {
  id: string;
  marca_id: string;
  variable_slug: string;
  content: string;
  status: PesquisaStatus;
  origin: PesquisaOrigem;
  plays: number | null;
  source_ref: SourceRef | null;
  created_at: string;
}

export interface PesquisaItemsPage {
  items: PesquisaItem[];
  total: number;
}

export interface PesquisaCounts {
  approved: number;
  pending: number;
  by_variable: Record<string, { approved: number; pending: number }>;
}

export interface AdicionarResult {
  saved: number;
  skipped: number;
  items: PesquisaItem[];
}

export interface ClassificarResult {
  saved: number;
  skipped: number;
  classified: Record<string, string[]>;
  unclassified: string[];
}

export type BulkAction = "approve" | "reject" | "delete";

export interface PesquisaFilters {
  marcaId: string | null;
  status: PesquisaStatus;
  variableSlug: string | null;
  sort: PesquisaSort;
  pageSize: number;
}

// ─── Keys ───────────────────────────────────────────────────────────────────

const BASE = "/api/media-creation/pesquisa";
export const PESQUISA_KEY = ["sw", "pesquisa"] as const;
const VARIABLES_KEY = [...PESQUISA_KEY, "variables"] as const;
const itemsKey = (f: PesquisaFilters) =>
  [...PESQUISA_KEY, "items", f.marcaId, f.status, f.variableSlug, f.sort, f.pageSize] as const;
const countsKey = (marcaId: string | null) => [...PESQUISA_KEY, "counts", marcaId] as const;

interface Envelope<T> {
  success?: boolean;
  ok?: boolean;
  data: T;
}

const unwrap = <T>(res: Envelope<T>): T => res.data;

// ─── Queries ────────────────────────────────────────────────────────────────

export function usePesquisaVariaveis() {
  const query = useQuery({
    queryKey: VARIABLES_KEY,
    queryFn: async () => unwrap(await api.get<Envelope<PesquisaVariable[]>>(`${BASE}/variables`)) ?? [],
    staleTime: 5 * 60_000,
  });
  return {
    ...query,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

export function usePesquisaItens(filters: PesquisaFilters) {
  const { marcaId, status, variableSlug, sort, pageSize } = filters;
  const query = useInfiniteQuery({
    queryKey: itemsKey(filters),
    enabled: !!marcaId,
    initialPageParam: 0,
    queryFn: async ({ pageParam }) => {
      const params = new URLSearchParams({
        marca_id: marcaId as string,
        status,
        sort,
        limit: String(pageSize),
        offset: String(pageParam),
      });
      if (variableSlug) params.set("variable_slug", variableSlug);
      return unwrap(await api.get<Envelope<PesquisaItemsPage>>(`${BASE}/items?${params.toString()}`));
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

export function usePesquisaCounts(marcaId: string | null) {
  const query = useQuery({
    queryKey: countsKey(marcaId),
    enabled: !!marcaId,
    queryFn: async () =>
      unwrap(
        await api.get<Envelope<PesquisaCounts>>(
          `${BASE}/items/counts?marca_id=${encodeURIComponent(marcaId as string)}`,
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

// ─── Mutations (each invalidates list + counts) ─────────────────────────────

function useInvalidatePesquisa() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: PESQUISA_KEY });
}

type ItensCache = { pages: PesquisaItemsPage[]; pageParams: unknown[] };
/** Every cached items list: `[…PESQUISA_KEY, "items", marcaId, status, variableSlug, sort, pageSize]`. */
const ITENS_KEY = [...PESQUISA_KEY, "items"] as const;
const marcaDaLista = (key?: QueryKey) => key?.[3];
const statusDaLista = (key?: QueryKey) => key?.[4];

export function useAdicionarItens() {
  const invalidate = useInvalidatePesquisa();
  return useMutation({ // noc-allow: invalidate-only — the server classifies and dedupes the lines and sorts each list (plays/recent): where (and whether) each new item lands in each cached list, and the counts, are its call
    mutationFn: async (v: { marca_id: string; variable_slug: string; lines: string[] }) =>
      unwrap(await api.post<Envelope<AdicionarResult>>(`${BASE}/items`, v)),
    onSuccess: invalidate,
  });
}

export function useClassificarItens() {
  const invalidate = useInvalidatePesquisa();
  return useMutation({ // noc-allow: invalidate-only — the server classifies free text into variables (many rows across lists); the response is a summary
    mutationFn: async (v: { marca_id: string; text: string }) =>
      unwrap(await api.post<Envelope<ClassificarResult>>(`${BASE}/items/classify`, v)),
    onSuccess: invalidate,
  });
}

/** Approve: the item leaves the pending lists at once; the approved lists place it (sorted server-side) on the settle. */
export function useAprovarItem() {
  return useCacheWriteMutation<PesquisaItem, string>({
    mutationFn: async (id) =>
      unwrap(await api.post<Envelope<PesquisaItem>>(`${BASE}/items/${encodeURIComponent(id)}/approve`)),
    targets: (id) => [
      {
        queryKey: ITENS_KEY,
        match: "prefix",
        optimistic: (old: ItensCache | undefined, _id, _ctx, key) =>
          statusDaLista(key) === "pending" ? infiniteOps.remove(old, id) : old,
        commit: (old: ItensCache | undefined, saved, _id, _ctx, key) =>
          statusDaLista(key) === saved.status ? infiniteOps.replace(old, id, saved) : infiniteOps.remove(old, id),
      },
    ],
    invalidate: [PESQUISA_KEY],
  });
}

/** Reject: the item belongs to neither the pending nor the approved list any more. */
export function useRejeitarItem() {
  return useCacheWriteMutation<PesquisaItem, string>({
    mutationFn: async (id) =>
      unwrap(await api.post<Envelope<PesquisaItem>>(`${BASE}/items/${encodeURIComponent(id)}/reject`)),
    targets: (id) => [
      {
        queryKey: ITENS_KEY,
        match: "prefix",
        commit: (old: ItensCache | undefined, saved, _id, _ctx, key) =>
          statusDaLista(key) === saved.status ? infiniteOps.replace(old, id, saved) : infiniteOps.remove(old, id),
      },
    ],
    invalidate: [PESQUISA_KEY],
  });
}

export function useExcluirItem() {
  return useCacheWriteMutation<void, string>({
    mutationFn: async (id) => {
      await api.delete(`${BASE}/items/${encodeURIComponent(id)}`);
    },
    targets: (id) => [
      {
        queryKey: ITENS_KEY,
        match: "prefix",
        optimistic: (old: ItensCache | undefined) => infiniteOps.remove(old, id),
      },
    ],
    invalidate: [PESQUISA_KEY],
  });
}

/** Bulk: approve takes the ids off the pending lists; reject / delete take them off every list. */
export function useAcaoEmMassa() {
  return useCacheWriteMutation<{ affected: number }, { marca_id: string; action: BulkAction; ids: string[] }>({
    mutationFn: async (v) =>
      unwrap(await api.post<Envelope<{ affected: number }>>(`${BASE}/items/bulk`, v)),
    targets: (v) => [
      {
        queryKey: ITENS_KEY,
        match: "prefix",
        optimistic: (old: ItensCache | undefined, _vars, _ctx, key) =>
          v.action === "approve" && statusDaLista(key) !== "pending"
            ? old
            : v.ids.reduce<ItensCache | undefined>((acc, id) => infiniteOps.remove(acc, id), old),
      },
    ],
    invalidate: [PESQUISA_KEY],
  });
}

/** Zero the research of a marca: all of its cached lists go blank at once. */
export function useZerarPesquisa() {
  return useCacheWriteMutation<{ deleted: number }, string>({
    mutationFn: async (marca_id) =>
      unwrap(await api.post<Envelope<{ deleted: number }>>(`${BASE}/items/empty`, { marca_id, confirm: true })),
    targets: (marcaId) => [
      {
        queryKey: ITENS_KEY,
        match: "prefix",
        predicate: (key) => marcaDaLista(key) === marcaId,
        optimistic: (old: ItensCache | undefined) =>
          infiniteOps.mapPages(old, (pg) => ({ ...(pg as PesquisaItemsPage), items: [], total: 0 })),
      },
    ],
    invalidate: [PESQUISA_KEY],
  });
}
