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
import { useQuery } from '@tanstack/react-query';
import { listOps, useCacheWriteMutation } from '../cache-writes';
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


function mapBalances(page: unknown, fn: (row: StockBalance) => StockBalance): unknown {
  if (!page || typeof page !== 'object' || !Array.isArray((page as Paginated<StockBalance>).data)) return page;
  const p = page as Paginated<StockBalance>;
  return { ...p, data: p.data.map(fn) };
}

/** Write the server's post-move numbers into the balance rows (of any cached page / filter) that a move touched. */
function applyMoves(page: unknown, moves: StockMove[]): unknown {
  return mapBalances(page, (row) => {
    const m = moves.find((x) => x.item_id === row.item_id && x.warehouse_id === row.warehouse_id);
    if (!m) return row;
    return {
      ...row,
      on_hand: m.on_hand_after,
      reserved: m.reserved_after,
      available: m.on_hand_after - m.reserved_after,
      avg_cost_cents: m.avg_cost_after_cents,
      value_cents: Math.round(m.on_hand_after * m.avg_cost_after_cents),
    };
  });
}

export function createInventoryHooks(api: InventoryApi) {
  const unwrap = async <T,>(p: Promise<InventoryEnvelope<T>>): Promise<T> => (await p).data;

  function useWarehouses(params: { active?: boolean } = {}) {
    const q = useQuery<Warehouse[]>({
      queryKey: [...inventoryKeys.warehouses, params],
      queryFn: () => unwrap(api.get(`${BASE}/warehouses`, params)),
      placeholderData: keep,
    });
    return signals(q);
  }
  /**
   * A new warehouse is drawn into the lists it belongs to (unfiltered + active-only; it is created active) once the
   * server answers — the code/default flag are server-decided; an edit is drawn on the click in every cached list.
   * Other filters converge on the background settle.
   */
  function useWarehouseMutations() {
    const listOf = (params: object) => ({
      queryKey: [...inventoryKeys.warehouses, params] as const,
      commit: (old: Warehouse[] | undefined, saved: Warehouse) => listOps.replace(old, saved.id, saved),
    });
    return {
      create: useCacheWriteMutation<Warehouse, WarehouseInput>({
        mutationFn: (b) => unwrap<Warehouse>(api.post(`${BASE}/warehouses`, b)),
        targets: [listOf({}), listOf({ active: true }), { queryKey: inventoryKeys.warehouses }],
      }),
      update: useCacheWriteMutation<Warehouse, WarehousePatch & { id: string }>({
        mutationFn: ({ id, ...b }) => unwrap<Warehouse>(api.patch(`${BASE}/warehouses/${id}`, b)),
        targets: ({ id, ...changes }) => [
          {
            queryKey: inventoryKeys.warehouses,
            match: 'prefix',
            optimistic: (old: Warehouse[] | undefined) => listOps.patch(old, id, changes as Partial<Warehouse>),
            commit: (old: Warehouse[] | undefined, saved: Warehouse) => listOps.patch(old, id, saved),
          },
        ],
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

  /**
   * A stock move answers with the rows it wrote, and each row carries the server's resulting `on_hand_after` /
   * `reserved_after` / `avg_cost_after_cents` — so the balance rows already on screen take those numbers the moment
   * the POST returns. What a move changes beyond that (kardex pages, valuation, low-stock flag) is derived on the
   * server and refreshes in the background.
   */
  function useStockMutations() {
    const settled = [inventoryKeys.kardex, inventoryKeys.valuation, inventoryKeys.lowStock];
    const balanceRows = { queryKey: inventoryKeys.balances, match: 'prefix' as const };
    const move = <V,>(post: (b: V) => Promise<MoveResult>) =>
      useCacheWriteMutation<MoveResult, V>({
        mutationFn: post,
        targets: [{ ...balanceRows, commit: (old: unknown, res: MoveResult) => applyMoves(old, res.moves) }],
        invalidate: settled,
      });
    return {
      receive: move<ReceiveInput>((b) => unwrap<MoveResult>(api.post(`${BASE}/receive`, b))),
      issue: move<IssueInput>((b) => unwrap<MoveResult>(api.post(`${BASE}/issue`, b))),
      adjust: move<AdjustInput>((b) => unwrap<MoveResult>(api.post(`${BASE}/adjust`, b))),
      transfer: move<TransferInput>((b) => unwrap<MoveResult>(api.post(`${BASE}/transfer`, b))),
      setMinQty: useCacheWriteMutation<{ item_id: string; warehouse_id: string; min_qty: number }, MinQtyInput>({
        mutationFn: (b) => unwrap<{ item_id: string; warehouse_id: string; min_qty: number }>(api.put(`${BASE}/settings`, b)),
        targets: [
          {
            ...balanceRows,
            commit: (old: unknown, res) =>
              mapBalances(old, (r) => (r.item_id === res.item_id && r.warehouse_id === res.warehouse_id ? { ...r, min_qty: res.min_qty } : r)),
          },
        ],
        // whether the row is now low on stock is the server's call
        invalidate: [inventoryKeys.lowStock],
      }),
    };
  }

  return { useWarehouses, useWarehouseMutations, useBalances, useKardex, useValuation, useLowStock, useStockMutations };
}

export type InventoryHooks = ReturnType<typeof createInventoryHooks>;
