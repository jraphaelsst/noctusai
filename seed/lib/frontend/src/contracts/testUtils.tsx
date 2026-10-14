/** Shared test helpers for the contracts organ (not exported from the barrel). */
import * as React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { makeRoutedApi } from '../organ-kit/testing';
import { createContractsHooks, type ContractsApi } from './hooks';
import type { Contract, ContractVersion } from './types';

export function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

export function wrapperFor(client: QueryClient = makeClient()) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

export const page = (rows: unknown[], extra: Record<string, unknown> = {}) => ({
  data: rows,
  pagination: { page: 1, page_size: 20, total: rows.length, ...extra },
});
export const ok = <T,>(data: T) => ({ data });

export function setup(routes: Record<string, unknown> = {}) {
  const api = makeRoutedApi<ContractsApi>(routes);
  return { api, hooks: createContractsHooks(api), Wrapper: wrapperFor() };
}

export function contract(over: Partial<Contract> = {}): Contract {
  return {
    id: 'c1', org_id: 'org', number: 'CT-1', title: 'Gestão de tráfego', party_id: null, party_name: 'Ana Souza', party_doc: '***.982.247-**',
    status: 'draft', billing_model: 'recurring', amount_cents: 150000, frequency: 'monthly', installments_count: null, due_day: 10,
    first_due_date: '2026-11-10', next_period_on: null, start_date: '2026-11-01', end_date: null, auto_renew: false, renewal_months: 12,
    retainer_minutes: null, excess_rate_cents: null, readjustment_index: 'none', readjustment_percent_bp: null, readjustment_every_months: 12,
    last_readjusted_on: null, notice_days: 30, penalty_cents: 0, penalty_bp: 0, penalty_applied_cents: null, document_body: null, version_n: 1,
    activated_at: null, suspended_at: null, suspension_reason: null, terminated_on: null, termination_reason: null, signature_status: 'none',
    signed_at: null, source_quote_id: null, notes: null, created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-01T00:00:00Z',
    terminable_from: '2026-12-01', readjustment_due_on: null, lapsed: false, lines: [], ...over,
  };
}

export function version(over: Partial<ContractVersion> = {}): ContractVersion {
  return { id: 'v1', contract_id: 'c1', version_n: 1, kind: 'initial', summary: 'Termos iniciais', changes: {}, effective_on: '2026-11-01', created_at: '2026-10-01T00:00:00Z', ...over };
}
