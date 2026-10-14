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
import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { ApiError, type ApiClient } from '../api';
import { keep, signals } from '../organ-kit/query';
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

  function useInvalidate() {
    const qc = useQueryClient();
    return (...keys: QueryKey[]) => Promise.all(keys.map((k) => qc.invalidateQueries({ queryKey: k })));
  }

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

  function useItemMutations() {
    const inv = useInvalidate();
    const done = () => inv(itemsKeys.all);
    return {
      create: useMutation({
        mutationFn: (body: ItemInput) => unwrap<Item>(api.post('/api/items', body)),
        onSuccess: done,
      }),
      update: useMutation({
        mutationFn: ({ id, ...body }: ItemPatch & { id: string }) => unwrap<Item>(api.patch(`/api/items/${id}`, body)),
        onSuccess: done,
      }),
      archive: useMutation({
        mutationFn: (id: string) => unwrap<Item>(api.post(`/api/items/${id}/archive`)),
        onSuccess: done,
      }),
      unarchive: useMutation({
        mutationFn: (id: string) => unwrap<Item>(api.post(`/api/items/${id}/unarchive`)),
        onSuccess: done,
      }),
    };
  }

  // ---- CSV ---------------------------------------------------------------
  function useExportItems() {
    return useMutation({
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
    const inv = useInvalidate();
    return useMutation({
      mutationFn: ({ file, updateExisting = false, dryRun = false }: { file: File; updateExisting?: boolean; dryRun?: boolean }) => {
        const form = new FormData();
        form.append('file', file);
        form.append('update_existing', String(updateExisting));
        form.append('dry_run', String(dryRun));
        return unwrap<ItemImportResult>(api.upload('/api/items/import', form));
      },
      onSuccess: (result) => (result.dry_run ? undefined : inv(itemsKeys.all)),
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
    const inv = useInvalidate();
    const done = () => inv(itemsKeys.categories);
    return {
      create: useMutation({
        mutationFn: (b: ItemCategoryInput) => unwrap<ItemCategory>(api.post('/api/items/categories', b)),
        onSuccess: done,
      }),
      update: useMutation({
        mutationFn: ({ id, ...b }: Partial<ItemCategoryInput> & { id: string; is_active?: boolean }) =>
          unwrap<ItemCategory>(api.patch(`/api/items/categories/${id}`, b)),
        onSuccess: done,
      }),
      remove: useMutation({
        mutationFn: (id: string) => api.delete(`/api/items/categories/${id}`),
        // an item list may be filtered by the removed category
        onSuccess: () => inv(itemsKeys.categories, itemsKeys.list),
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
