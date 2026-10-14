/** Shared fixtures for the ERP dashboard tests (not exported from the barrel). */
import * as React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { makeRoutedApi } from '../organ-kit/testing';
import { createFinanceHooks, type FinanceApi } from '../finance/hooks';
import { createInventoryHooks, type InventoryApi } from '../inventory/hooks';
import { createPurchasingHooks, type PurchasingApi } from '../purchasing/hooks';
import { createContractsHooks, type ContractsApi } from '../contracts/hooks';
import { createQuotesHooks, type QuotesApi } from '../quotes/hooks';

export const NOW = new Date(2026, 9, 14); // 14 Oct 2026

export function wrapperFor(client: QueryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

export const page = (rows: unknown[], total = rows.length) => ({ data: rows, pagination: { page: 1, page_size: 100, total } });

export const financeApi = () =>
  makeRoutedApi<FinanceApi>({
    'GET /api/finance/reports/dre': { data: { net_result_cents: 123_456 } },
    'GET /api/finance/reports/cashflow': {
      data: {
        buckets: [], closing_realized_balance_cents: 500_000,
        totals: { realized_in_cents: 0, realized_out_cents: 0, projected_in_cents: 300_000, projected_out_cents: 200_000 },
      },
    },
    'GET /api/finance/reports/aging': { data: { counterparties: [{}, {}], totals: { total_cents: 70_000, buckets: {} } } },
    'GET /api/finance/entries': page([{ amount_cents: 10_000, settled_cents: 0, status: 'open' }], 1),
  });

export const inventoryApi = () =>
  makeRoutedApi<InventoryApi>({
    'GET /api/inventory/low-stock': { data: [{}, {}, {}] },
    'GET /api/inventory/valuation': { data: { method: 'average_cost', total_cents: 99_900, items: 4, by_warehouse: [] } },
  });

export const purchasingApi = () =>
  makeRoutedApi<PurchasingApi>({
    'GET /api/purchasing/orders': (_p: string, params?: unknown) => {
      const status = (params as { status?: string } | undefined)?.status;
      return page([], { draft: 2, approved: 1, sent: 3, partially_received: 1 }[status ?? ''] ?? 0);
    },
  });

export const contractsApi = () =>
  makeRoutedApi<ContractsApi>({
    'GET /api/contracts': (_p: string, params?: unknown) => {
      if ((params as { expiring_within_days?: number } | undefined)?.expiring_within_days) return page([], 2);
      return page([
        { id: 'c1', amount_cents: 100_000, next_period_on: '2026-10-20' },
        { id: 'c2', amount_cents: 50_000, next_period_on: '2026-12-20' },
      ]);
    },
  });

export const quotesApi = () =>
  makeRoutedApi<QuotesApi>({
    'GET /api/quotes': (_p: string, params?: unknown) => {
      const status = (params as { status?: string } | undefined)?.status;
      if (status === 'sent') return page([{ id: 'q1', total_cents: 20_000, valid_until: '2026-10-18' }, { id: 'q2', total_cents: 30_000, valid_until: '2026-12-01' }]);
      return page([]);
    },
  });

export const hooks = {
  finance: (api = financeApi()) => createFinanceHooks(api),
  inventory: (api = inventoryApi()) => createInventoryHooks(api),
  purchasing: (api = purchasingApi()) => createPurchasingHooks(api),
  contracts: (api = contractsApi()) => createContractsHooks(api),
  quotes: (api = quotesApi()) => createQuotesHooks(api),
};
