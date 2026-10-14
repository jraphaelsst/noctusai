/** Shared test helpers for the items organ (not exported from the barrel). */
import * as React from 'react';
import { vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ItemsApi } from './hooks';
import type { Item, ItemCategory } from './types';

export const EAN13 = '7891000100103';

export function makeApi() {
  return {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    upload: vi.fn(),
    download: vi.fn(),
  } as unknown as { [K in keyof ItemsApi]: ReturnType<typeof vi.fn> } & ItemsApi;
}

export function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

export function wrapperFor(client: QueryClient = makeClient()) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

export const page = <T,>(rows: T[], total = rows.length, pageNo = 1, size = 20) => ({
  data: rows,
  pagination: { page: pageNo, page_size: size, total },
});

export function item(over: Partial<Item> = {}): Item {
  return {
    id: 'i1', org_id: 'o', sku: 'PAR-1', name: 'Parafuso', description: null, item_type: 'goods', unit: 'UN',
    category_id: null, ncm: null, cest: null, cfop_default: null, origem: null, gtin: null, cost_cents: 150,
    price_cents: 300, weight_g: null, length_mm: null, width_mm: null, height_mm: null, is_active: true,
    created_at: '2026-10-14T00:00:00Z', updated_at: '2026-10-14T00:00:00Z', ...over,
  };
}

export function category(over: Partial<ItemCategory> = {}): ItemCategory {
  return { id: 'c1', org_id: 'o', parent_id: null, name: 'Ferragens', is_active: true, created_at: '', updated_at: '', ...over };
}

/** Route `api.get` by path so one mock serves the list, the detail and the categories. */
export function routeGet(api: ReturnType<typeof makeApi>, routes: Record<string, unknown>) {
  api.get.mockImplementation(async (path: string) => {
    const key = Object.keys(routes).find((k) => path === k) ?? Object.keys(routes).find((k) => path.startsWith(k));
    if (key === undefined) throw new Error(`unrouted GET ${path}`);
    const v = routes[key];
    return typeof v === 'function' ? (v as () => unknown)() : v;
  });
}
