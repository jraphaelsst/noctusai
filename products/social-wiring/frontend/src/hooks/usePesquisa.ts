/**
 * Minha Pesquisa — TanStack Query hooks over `/api/media-creation/pesquisa`
 * (build contract: projects/core-studio/specs/pesquisa-contract.md §3).
 *
 * Responses arrive wrapped in `success_response` ({success, data}); we unwrap
 * at the boundary. Loading rule (lying-loading-state.md): every query hook
 * returns `showSkeleton = isPending && !data` and `isRefreshing = isFetching
 * && !!data`, with `placeholderData` on key changes — never `isLoading`.
 * Every mutation invalidates the whole `["sw","pesquisa"]` family (list +
 * counts) so the page never shows stale numbers.
 */
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  keepPreviousData,
} from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

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

export interface PesquisaItem {
  id: string;
  marca_id: string;
  variable_slug: string;
  content: string;
  status: PesquisaStatus;
  origin: PesquisaOrigem;
  plays: number | null;
  source_ref: object | null;
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

export function useAdicionarItens() {
  const invalidate = useInvalidatePesquisa();
  return useMutation({
    mutationFn: async (v: { marca_id: string; variable_slug: string; lines: string[] }) =>
      unwrap(await api.post<Envelope<AdicionarResult>>(`${BASE}/items`, v)),
    onSuccess: invalidate,
  });
}

export function useClassificarItens() {
  const invalidate = useInvalidatePesquisa();
  return useMutation({
    mutationFn: async (v: { marca_id: string; text: string }) =>
      unwrap(await api.post<Envelope<ClassificarResult>>(`${BASE}/items/classify`, v)),
    onSuccess: invalidate,
  });
}

export function useAprovarItem() {
  const invalidate = useInvalidatePesquisa();
  return useMutation({
    mutationFn: async (id: string) =>
      unwrap(await api.post<Envelope<PesquisaItem>>(`${BASE}/items/${encodeURIComponent(id)}/approve`)),
    onSuccess: invalidate,
  });
}

export function useRejeitarItem() {
  const invalidate = useInvalidatePesquisa();
  return useMutation({
    mutationFn: async (id: string) =>
      unwrap(await api.post<Envelope<PesquisaItem>>(`${BASE}/items/${encodeURIComponent(id)}/reject`)),
    onSuccess: invalidate,
  });
}

export function useExcluirItem() {
  const invalidate = useInvalidatePesquisa();
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`${BASE}/items/${encodeURIComponent(id)}`);
    },
    onSuccess: invalidate,
  });
}

export function useAcaoEmMassa() {
  const invalidate = useInvalidatePesquisa();
  return useMutation({
    mutationFn: async (v: { marca_id: string; action: BulkAction; ids: string[] }) =>
      unwrap(await api.post<Envelope<{ affected: number }>>(`${BASE}/items/bulk`, v)),
    onSuccess: invalidate,
  });
}

export function useZerarPesquisa() {
  const invalidate = useInvalidatePesquisa();
  return useMutation({
    mutationFn: async (marca_id: string) =>
      unwrap(await api.post<Envelope<{ deleted: number }>>(`${BASE}/items/empty`, { marca_id, confirm: true })),
    onSuccess: invalidate,
  });
}
