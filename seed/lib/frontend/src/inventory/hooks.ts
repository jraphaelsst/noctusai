/**
 * `createInventoryHooks(api)` — TanStack Query hooks for the inventory API (`/api/inventory`).
 *
 * 🔴 Loading contract (`KB § PATTERNS/frontend/lying-loading-state.md`): every read hook returns
 * `showSkeleton = isPending && !data` (first load only) and `isRefreshing = isFetching && !!data`
 * (indicator only). Never `isLoading`, never a bare `isFetching` gate. Lists whose key changes keep
 * `placeholderData: (prev) => prev`. id-keyed reads that are authorization-scoped do not.
 *
 * Mutations reject with `ApiError` (the caller renders it; `inventoryErrorMessage` maps the stable
 * codes) and invalidate every read they can change: a stock move changes balances, kardex, valuation
 * and low-stock at once.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type ApiClient } from '../api';
import { errorMessage, keep, signals } from '../organ-kit/query';
import { defaultInventoryT, type InventoryTranslate } from './i18n';
import type {
  AdjustInput,
  BalanceParams,
  InventoryEnvelope,
  IssueInput,
  KardexParams,
  MinQtyInput,
  MoveResult,
  Paginated,
  ReceiveInput,
  StockBalance,
  StockMove,
  TransferInput,
  Valuation,
  Warehouse,
  WarehouseInput,
  WarehousePatch,
} from './types';

export type InventoryApi = Pick<ApiClient, 'get' | 'post' | 'put' | 'patch' | 'delete'>;

const BASE = '/api/inventory';

/** Namespaced query keys (exported so hosts can invalidate precisely). */
export const inventoryKeys = {
  all: ['inventory'] as const,
  warehouses: ['inventory', 'warehouses'] as const,
  balances: ['inventory', 'balances'] as const,
  kardex: ['inventory', 'kardex'] as const,
  valuation: ['inventory', 'valuation'] as const,
  lowStock: ['inventory', 'low-stock'] as const,
};

export { errorMessage };

/** pt-BR copy for the stable backend error codes; falls back to the server message. */
export function inventoryErrorMessage(err: unknown, t: InventoryTranslate = defaultInventoryT): string {
  if (err instanceof ApiError && err.code) {
    const mapped = t(`error.${err.code}`);
    if (mapped !== `error.${err.code}`) return mapped;
  }
  return errorMessage(err);
}


export function createInventoryHooks(api: InventoryApi) {
  const unwrap = async <T,>(p: Promise<InventoryEnvelope<T>>): Promise<T> => (await p).data;

  function useInvalidateStock() {
    const qc = useQueryClient();
    return () =>
      Promise.all(
        [inventoryKeys.balances, inventoryKeys.kardex, inventoryKeys.valuation, inventoryKeys.lowStock].map((k) =>
          qc.invalidateQueries({ queryKey: k }),
        ),
      );
  }

  function useWarehouses(params: { active?: boolean } = {}) {
    const q = useQuery<Warehouse[]>({
      queryKey: [...inventoryKeys.warehouses, params],
      queryFn: () => unwrap(api.get(`${BASE}/warehouses`, params)),
      placeholderData: keep,
    });
    return signals(q);
  }
  function useWarehouseMutations() {
    const qc = useQueryClient();
    const done = () => qc.invalidateQueries({ queryKey: inventoryKeys.warehouses });
    return {
      create: useMutation({
        mutationFn: (b: WarehouseInput) => unwrap<Warehouse>(api.post(`${BASE}/warehouses`, b)),
        onSuccess: done,
      }),
      update: useMutation({
        mutationFn: ({ id, ...b }: WarehousePatch & { id: string }) => unwrap<Warehouse>(api.patch(`${BASE}/warehouses/${id}`, b)),
        onSuccess: done,
      }),
    };
  }

  function useBalances(params: BalanceParams = {}) {
    const q = useQuery<Paginated<StockBalance>>({
      queryKey: [...inventoryKeys.balances, params],
      queryFn: () => api.get(`${BASE}/balances`, params),
      placeholderData: keep,
    });
    return signals(q);
  }
  function useKardex(params: KardexParams | null) {
    // Item-keyed history: no placeholderData across ITEMS (another item's rows must never show under this one).
    const q = useQuery<Paginated<StockMove>>({
      queryKey: [...inventoryKeys.kardex, params],
      queryFn: () => api.get(`${BASE}/kardex`, params ?? {}),
      enabled: !!params?.item_id,
    });
    return signals(q);
  }
  function useValuation(warehouseId?: string) {
    const q = useQuery<Valuation>({
      queryKey: [...inventoryKeys.valuation, warehouseId ?? null],
      queryFn: () => unwrap(api.get(`${BASE}/valuation`, warehouseId ? { warehouse_id: warehouseId } : undefined)),
      placeholderData: keep,
    });
    return signals(q);
  }
  function useLowStock() {
    const q = useQuery<StockBalance[]>({
      queryKey: inventoryKeys.lowStock,
      queryFn: () => unwrap(api.get(`${BASE}/low-stock`)),
    });
    return signals(q);
  }

  function useStockMutations() {
    const inv = useInvalidateStock();
    return {
      receive: useMutation({ mutationFn: (b: ReceiveInput) => unwrap<MoveResult>(api.post(`${BASE}/receive`, b)), onSuccess: inv }),
      issue: useMutation({ mutationFn: (b: IssueInput) => unwrap<MoveResult>(api.post(`${BASE}/issue`, b)), onSuccess: inv }),
      adjust: useMutation({ mutationFn: (b: AdjustInput) => unwrap<MoveResult>(api.post(`${BASE}/adjust`, b)), onSuccess: inv }),
      transfer: useMutation({ mutationFn: (b: TransferInput) => unwrap<MoveResult>(api.post(`${BASE}/transfer`, b)), onSuccess: inv }),
      setMinQty: useMutation({
        mutationFn: (b: MinQtyInput) => unwrap<{ item_id: string; warehouse_id: string; min_qty: number }>(api.put(`${BASE}/settings`, b)),
        onSuccess: inv,
      }),
    };
  }

  return { useWarehouses, useWarehouseMutations, useBalances, useKardex, useValuation, useLowStock, useStockMutations };
}

export type InventoryHooks = ReturnType<typeof createInventoryHooks>;
