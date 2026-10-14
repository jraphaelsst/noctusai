/** Shared test helpers for the purchasing organ (not exported from the barrel). */
import * as React from 'react';
import { vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PurchasingApi } from './hooks';
import type { PurchaseOrder, PurchaseOrderLine, PurchaseReceipt } from './types';

export function makeApi() {
  return { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } as unknown as {
    [K in keyof PurchasingApi]: ReturnType<typeof vi.fn>;
  } & PurchasingApi;
}

export function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

export function wrapperFor(client: QueryClient = makeClient()) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

export const ORDER_ID = 'ord-1';
export const LINE1 = 'line-1';
export const LINE2 = 'line-2';

export const line = (over: Partial<PurchaseOrderLine> = {}): PurchaseOrderLine => ({
  id: LINE1, org_id: 'o', order_id: ORDER_ID, line_no: 1, item_id: 'item-1', description: 'Tinta acrílica', unit: 'L', qty: 10, unit_cost_cents: 1000,
  line_total_cents: 10000, received_qty: 0, ...over,
});

export const order = (over: Partial<PurchaseOrder> = {}): PurchaseOrder => ({
  id: ORDER_ID, org_id: 'o', number: 7, status: 'draft', party_id: 'party-1', supplier_name: 'Tintas Ltda', warehouse_id: 'wh-1',
  expected_date: '2026-10-20', installments_count: 2, first_due_days: 30, interval_days: 15, freight_cents: 1000, discount_cents: 500,
  other_cents: 0, goods_cents: 10000, total_cents: 10500, notes: null, approved_by: null, approved_at: null, sent_at: null,
  cancelled_at: null, cancel_reason: null, created_at: '', updated_at: '2026-10-14T10:00:00Z', ...over,
});

export const detail = (over: Partial<PurchaseOrder> = {}): PurchaseOrder => order({ lines: [line()], receipts: [], ...over });

export const receipt = (over: Partial<PurchaseReceipt> = {}): PurchaseReceipt => ({
  id: 'rc-1', org_id: 'o', order_id: ORDER_ID, receipt_no: 1, received_on: '2026-10-14', note: null, goods_cents: 10000, adjustment_cents: 500,
  total_cents: 10500, stock_posted_at: '2026-10-14T12:00:00Z', finance_posted_at: '2026-10-14T12:00:00Z', posting_error: null, posted: true,
  created_at: '', ...over,
});

export const page = <T,>(rows: T[]) => ({ data: rows, pagination: { page: 1, page_size: 20, total: rows.length } });

/** Route `api.get` by path suffix so several hooks in one organ each get their payload. */
export function routeGet(api: ReturnType<typeof makeApi>, routes: Record<string, unknown>) {
  api.get.mockImplementation((path: string) => {
    const hit = Object.entries(routes).find(([p]) => path.endsWith(p));
    return hit ? Promise.resolve(hit[1]) : Promise.reject(new Error(`unrouted GET ${path}`));
  });
}
