/** Shared test helpers for the inventory organ (not exported from the barrel). */
import * as React from 'react';
import { vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { InventoryApi } from './hooks';
import type { StockBalance, StockMove, Warehouse } from './types';

export function makeApi() {
  return { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } as unknown as {
    [K in keyof InventoryApi]: ReturnType<typeof vi.fn>;
  } & InventoryApi;
}

export function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

export function wrapperFor(client: QueryClient = makeClient()) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

export const WH1 = 'wh-1';
export const WH2 = 'wh-2';
export const ITEM = 'item-aaaaaaaa-1';

export const warehouse = (over: Partial<Warehouse> = {}): Warehouse => ({
  id: WH1, org_id: 'o', name: 'Matriz', code: 'MTZ', is_default: true, active: true, address: {}, created_at: '', updated_at: '', ...over,
});

export const balance = (over: Partial<StockBalance> = {}): StockBalance => ({
  org_id: 'o', item_id: ITEM, warehouse_id: WH1, on_hand: 10, reserved: 2, available: 8, avg_cost_cents: 150, value_cents: 1500,
  min_qty: null, low_stock: false, updated_at: '', ...over,
});

export const move = (over: Partial<StockMove> = {}): StockMove => ({
  id: 'm1', seq: 1, org_id: 'o', item_id: ITEM, warehouse_id: WH1, kind: 'in', qty: 10, unit_cost_cents: 150, source: 'manual',
  source_ref: null, transfer_group: null, note: null, on_hand_after: 10, reserved_after: 0, avg_cost_after_cents: 150,
  occurred_at: '2026-10-14T12:00:00Z', created_by: null, ...over,
});

export const page = <T,>(rows: T[]) => ({ data: rows, pagination: { page: 1, page_size: 50, total: rows.length } });

/** Route `api.get` by path so several hooks in one organ each get their payload. */
export function routeGet(api: ReturnType<typeof makeApi>, routes: Record<string, unknown>) {
  api.get.mockImplementation((path: string) => {
    const hit = Object.entries(routes).find(([p]) => path.endsWith(p));
    return hit ? Promise.resolve(hit[1]) : Promise.reject(new Error(`unrouted GET ${path}`));
  });
}
