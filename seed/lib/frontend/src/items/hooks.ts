/**
 * `createItemsHooks(api)` — TanStack Query hooks for the items API (`/api/items`, backend organ
 * `noctusai_lib.domain.items`). Pass the host's authenticated seed `ApiClient`; `{data}` /
 * `{data, pagination}` envelopes are unwrapped here.
 *
 * 🔴 Loading contract (`KB § PATTERNS/frontend/lying-loading-state.md`): every read hook returns
 * `showSkeleton = isPending && !data` (first load only) and `isRefreshing = isFetching && !!data`
 * (indicator only, never an early return). Never `isLoading`, never a bare `isFetching` gate. The list
 * (key changes with page/filters/search) keeps `placeholderData: (prev) => prev`. The detail query is
 * keyed by id and deliberately has no placeholderData (a previous item must not show under a new id).
 *
 * Errors are never swallowed: queries expose `error`, mutations reject with `ApiError`.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { listOps, useCacheWriteMutation } from '../cache-writes';
import { ApiError, type ApiClient } from '../api';
import { keep, signals } from '../organ-kit/query';
import { pageOps } from '../organ-kit/page-ops';
import type {
  Item,
  ItemCategory,
  ItemCategoryInput,
  ItemImportResult,
  ItemInput,
  ItemPatch,
  ItemsEnvelope,
  ItemsPage,
  ItemType,
} from './types';

/** The subset of the seed `ApiClient` the items hooks need. */
export type ItemsApi = Pick<ApiClient, 'get' | 'post' | 'patch' | 'delete' | 'upload' | 'download'>;

export interface ItemListParams {
  page?: number;
  q?: string;
  item_type?: ItemType | '';
  /** `''` = all, `'true'` = active only, `'false'` = archived only. */
  active?: '' | 'true' | 'false';
  category_id?: string;
}

export const ITEMS_PAGE_SIZE = 20;

/** Namespaced query keys (exported so hosts can invalidate precisely). */
export const itemsKeys = {
  all: ['items'] as const,
  list: ['items', 'list'] as const,
  item: (id: string) => ['items', 'detail', id] as const,
  categories: ['items', 'categories'] as const,
};

export function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/** `{error:{code,message,details:{field}}}` of an `ApiError`, for per-field display. */
export function apiFieldError(err: unknown): { field: string | null; code: string | null; message: string } | null {
  if (!(err instanceof ApiError)) return null;
  const body = err.body as { error?: { message?: unknown; details?: { field?: unknown } } } | undefined;
  const field = body?.error?.details?.field;
  const message = body?.error?.message;
  return {
    field: typeof field === 'string' ? field : null,
    code: err.code,
    message: typeof message === 'string' ? message : errorMessage(err),
  };
}

/** Row problems of a `422 importacao_invalida`, if that is what `err` is. */
export function importRowErrors(err: unknown): { rows: import('./types').ItemImportRowError[]; total: number } | null {
  if (!(err instanceof ApiError) || err.code !== 'importacao_invalida') return null;
  const body = err.body as { error?: { details?: { errors?: unknown; error_count?: unknown } } } | undefined;
  const rows = body?.error?.details?.errors;
  if (!Array.isArray(rows)) return null;
  const count = body?.error?.details?.error_count;
  return { rows: rows as import('./types').ItemImportRowError[], total: typeof count === 'number' ? count : rows.length };
}


function listQuery(params: ItemListParams): Record<string, string | number> {
  const out: Record<string, string | number> = { page: params.page ?? 1, page_size: ITEMS_PAGE_SIZE };
  if (params.q) out.q = params.q;
  if (params.item_type) out.item_type = params.item_type;
  if (params.active) out.active = params.active;
  if (params.category_id) out.category_id = params.category_id;
  return out;
}

export function createItemsHooks(api: ItemsApi) {
  const unwrap = async <T,>(p: Promise<ItemsEnvelope<T>>): Promise<T> => (await p).data;

  // ---- items -------------------------------------------------------------
  function useItems(params: ItemListParams = {}) {
    const q = useQuery<ItemsPage<Item>>({
      queryKey: [...itemsKeys.list, params],
      queryFn: () => api.get<ItemsPage<Item>>('/api/items', listQuery(params)),
      placeholderData: keep,
    });
    return signals(q);
  }

  function useItem(id: string | null | undefined) {
    const q = useQuery<Item>({
      queryKey: itemsKeys.item(id ?? ''),
      queryFn: () => unwrap<Item>(api.get(`/api/items/${id}`)),
      enabled: !!id,
    });
    return signals(q);
  }

  /**
   * Item writes (KB § PATTERNS/frontend/mutation-cache-writes.md). The server answers with the saved row, so an
   * edit is written into the detail AND into every cached page/filter that shows the row (`pageOps`, prefix match);
   * a NEW row is only seeded into its detail — which page / filter / sort position it belongs to is the server's
   * call, so the lists converge on the background settle. Categories are untouched by an item write.
   */
  function useItemMutations() {
    const qc = useQueryClient();
    const listTarget = { queryKey: itemsKeys.list, match: 'prefix' as const };
    const savedInto = (id: string) => ({
      queryKey: itemsKeys.item(id),
      commit: (_old: Item | undefined, saved: Item) => saved,
    });
    const savedRow = (id: string) => ({
      ...listTarget,
      commit: (old: unknown, saved: Item) => pageOps.replace(old, id, saved),
    });
    const setActive = (action: 'archive' | 'unarchive') =>
      useCacheWriteMutation<Item, string>({
        mutationFn: (id) => unwrap<Item>(api.post(`/api/items/${id}/${action}`)),
        // the flag is predictable: draw it on the click (an `active` filter then drops the row on settle)
        targets: (id) => [
          {
            queryKey: itemsKeys.item(id),
            optimistic: (old: Item | undefined) => listOps.merge(old, { is_active: action === 'unarchive' }),
            commit: (_old: Item | undefined, saved: Item) => saved,
          },
          {
            ...listTarget,
            optimistic: (old: unknown) => pageOps.patch(old, id, { is_active: action === 'unarchive' }),
            commit: (old: unknown, saved: Item) => pageOps.replace(old, id, saved),
          },
        ],
      });
    return {
      create: useCacheWriteMutation<Item, ItemInput>({
        mutationFn: (body) => unwrap<Item>(api.post('/api/items', body)),
        targets: [listTarget],
        onSuccess: (saved) => {
          qc.setQueryData(itemsKeys.item(saved.id), saved);
        },
      }),
      update: useCacheWriteMutation<Item, ItemPatch & { id: string }>({
        mutationFn: ({ id, ...body }) => unwrap<Item>(api.patch(`/api/items/${id}`, body)),
        targets: ({ id }) => [savedInto(id), savedRow(id)],
      }),
      archive: setActive('archive'),
      unarchive: setActive('unarchive'),
    };
  }

  // ---- CSV ---------------------------------------------------------------
  function useExportItems() {
    return useMutation({ // noc-allow: invalidate-only — CSV download: reads nothing from the cache and changes no server state
      mutationFn: (params: Omit<ItemListParams, 'page'> = {}) => {
        const qs = new URLSearchParams(
          Object.entries({ q: params.q, item_type: params.item_type, active: params.active, category_id: params.category_id })
            .filter(([, v]) => v !== undefined && v !== null && v !== '')
            .map(([k, v]) => [k, String(v)]),
        ).toString();
        return api.download(`/api/items/export.csv${qs ? `?${qs}` : ''}`);
      },
    });
  }

  function useImportItems() {
    const qc = useQueryClient();
    return useMutation({ // noc-allow: invalidate-only — a bulk CSV import answers with counts only; which rows landed on which page/filter is the server's, so the item lists re-read

      mutationFn: ({ file, updateExisting = false, dryRun = false }: { file: File; updateExisting?: boolean; dryRun?: boolean }) => {
        const form = new FormData();
        form.append('file', file);
        form.append('update_existing', String(updateExisting));
        form.append('dry_run', String(dryRun));
        return unwrap<ItemImportResult>(api.upload('/api/items/import', form));
      },
      onSuccess: (result) => (result.dry_run ? undefined : qc.invalidateQueries({ queryKey: itemsKeys.all })),
    });
  }

  // ---- categories --------------------------------------------------------
  function useItemCategories() {
    const q = useQuery<ItemCategory[]>({
      queryKey: itemsKeys.categories,
      queryFn: () => unwrap<ItemCategory[]>(api.get('/api/items/categories')),
    });
    return signals(q);
  }

  function useItemCategoryMutations() {
    return {
      create: useCacheWriteMutation<ItemCategory, ItemCategoryInput>({
        mutationFn: (b) => unwrap<ItemCategory>(api.post('/api/items/categories', b)),
        targets: [{ queryKey: itemsKeys.categories, commit: (old, saved) => listOps.replace(old, saved.id, saved) }],
      }),
      update: useCacheWriteMutation<ItemCategory, Partial<ItemCategoryInput> & { id: string; is_active?: boolean }>({
        mutationFn: ({ id, ...b }) => unwrap<ItemCategory>(api.patch(`/api/items/categories/${id}`, b)),
        targets: ({ id, ...changes }) => [
          {
            queryKey: itemsKeys.categories,
            optimistic: (old: ItemCategory[] | undefined) => listOps.patch(old, id, changes),
            commit: (old, saved) => listOps.replace(old, saved.id, saved),
          },
        ],
      }),
      remove: useCacheWriteMutation<unknown, string>({
        mutationFn: (id) => api.delete(`/api/items/categories/${id}`),
        targets: (id) => [{ queryKey: itemsKeys.categories, optimistic: (old) => listOps.remove(old, id) }],
        // an item list may be filtered by the removed category
        invalidate: [itemsKeys.list],
      }),
    };
  }

  return {
    useItems,
    useItem,
    useItemMutations,
    useExportItems,
    useImportItems,
    useItemCategories,
    useItemCategoryMutations,
  };
}

export type ItemsHooks = ReturnType<typeof createItemsHooks>;
