/** Shared test helpers for the finance organ (not exported from the barrel). */
import * as React from 'react';
import { vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiError } from '../api';
import { createFinanceHooks, type FinanceApi } from './hooks';
import type { FinanceAccount, FinanceCategory, FinanceEntry, CostCenter } from './types';

type Handler = unknown | ((path: string, arg?: unknown) => unknown);

/**
 * Routed fake `ApiClient`: `routes['GET /api/finance/accounts']` is a value (resolved) or a function
 * `(path, argOrParams) => value` (may throw / return a rejected promise). An unrouted call REJECTS loudly
 * (a test must declare every endpoint it touches). Every call is recorded on the `vi.fn` mocks.
 */
export function makeRoutedApi(routes: Record<string, Handler> = {}) {
  const table = { ...routes };
  const run = (method: string) =>
    vi.fn(async (path: string, arg?: unknown) => {
      const clean = path.split('?')[0];
      const handler = table[`${method} ${clean}`] ?? table[`${method} ${path}`];
      if (handler === undefined) throw new ApiError(404, `unrouted ${method} ${path}`);
      return typeof handler === 'function' ? (handler as (p: string, a?: unknown) => unknown)(path, arg) : handler;
    });
  const api = {
    get: run('GET'),
    post: run('POST'),
    put: run('PUT'),
    patch: run('PATCH'),
    delete: run('DELETE'),
    upload: run('UPLOAD'),
    download: vi.fn(async (_path: string) => new Blob(['x'])),
  };
  return Object.assign(api as unknown as FinanceApi & typeof api, {
    routes: table,
    route(key: string, handler: Handler) {
      table[key] = handler;
    },
  });
}

export function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

export function wrapperFor(client: QueryClient = makeClient()) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

export function hooksFor(api: FinanceApi) {
  return createFinanceHooks(api);
}

export const ok = <T,>(data: T) => ({ data });
export const page = <T,>(rows: T[], extra: Partial<{ page: number; page_size: number; total: number }> = {}) => ({
  data: rows,
  pagination: { page: 1, page_size: 20, total: rows.length, ...extra },
});

// ---- fixtures (a small believable store) ----
export const ACC_BANK: FinanceAccount = {
  id: 'acc-bank', name: 'Itaú', kind: 'checking', bank_code: '341', agency: '0001', number: '123-4',
  opening_balance_cents: 100_000, opening_date: '2026-01-01', gateway: null, active: true,
};
export const ACC_GW: FinanceAccount = {
  id: 'acc-gw', name: 'Asaas', kind: 'gateway', bank_code: null, agency: null, number: null,
  opening_balance_cents: 0, opening_date: null, gateway: 'asaas', active: true,
};
export const CAT_SALES: FinanceCategory = {
  id: 'cat-sales', parent_id: null, name: 'Vendas', direction: 'income', is_default: true, active: true, dre_line: 'gross_revenue', behavior: 'variable',
};
export const CAT_RENT: FinanceCategory = {
  id: 'cat-rent', parent_id: null, name: 'Aluguel', direction: 'expense', is_default: true, active: true, dre_line: null, behavior: null,
};
export const CAT_RENT_SUB: FinanceCategory = {
  id: 'cat-rent-sub', parent_id: 'cat-rent', name: 'Condomínio', direction: 'expense', is_default: false, active: true, dre_line: 'administrative_expenses', behavior: 'fixed',
};
export const CAT_TRANSFER: FinanceCategory = {
  id: 'cat-tr', parent_id: null, name: 'Entre contas', direction: 'transfer', is_default: true, active: true,
};
export const CC: CostCenter = { id: 'cc-1', code: 'LOJA', name: 'Loja', active: true };

export function entry(over: Partial<FinanceEntry> = {}): FinanceEntry {
  return {
    id: 'e1', direction: 'receivable', status: 'open', overdue: false, description: 'Pedido #100',
    counterparty_name: 'Maria', counterparty_doc: '***.456.789-**', category_id: 'cat-sales', cost_center_id: null,
    expected_account_id: 'acc-bank', competence_month: '2026-10-01', due_date: '2026-10-20', amount_cents: 10_000,
    settled_cents: 0, source: 'manual', source_ref: null, notes: null, ...over,
  };
}

/** The reference reads every screen needs; spread into a `makeRoutedApi` table. */
export function baseRoutes(): Record<string, Handler> {
  return {
    'GET /api/finance/accounts': ok([ACC_BANK, ACC_GW]),
    'GET /api/finance/categories': ok([CAT_SALES, CAT_RENT, CAT_RENT_SUB, CAT_TRANSFER]),
    'GET /api/finance/cost-centers': ok([CC]),
  };
}
