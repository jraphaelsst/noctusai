/**
 * Test harness for the credit pages: a recording fake HTTP client behind the real
 * `createCreditsApi`, injected with `CreditsApiProvider` — no module mocking of our code.
 */
import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { CreditsApiProvider, createCreditsApi } from '../lib/credits';
import { fakeHttp, type FakeHttp, type Route } from './billing-harness';

export { fakeHttp, type FakeHttp, type Route };

export function renderWithCredits(http: FakeHttp, ui: ReactNode, client?: QueryClient) {
  const qc = client ?? new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <CreditsApiProvider value={createCreditsApi(http)}>
        <MemoryRouter>{ui}</MemoryRouter>
      </CreditsApiProvider>
    </QueryClientProvider>
  );
}

export const WALLET = {
  exists: true, mode: 'prepaid', balance_credits: 12500, balance_brl: 125, overdraft_limit_credits: 0,
  alert_thresholds: [0.5, 0.8, 1], alert_base_credits: 20000, consumed_pct: 0.375, credit_unit_brl: 0.01,
  blocked: false,
};

export const USAGE = {
  window: { from: '2026-10-01T00:00:00Z', to: '2026-10-30T00:00:00Z' },
  credit_unit_brl: 0.01,
  totals: { calls: 3, input_tokens: 3000, output_tokens: 1500, tokens: 4500, credits: 3500, brl: 35, pending_calls: 1 },
  per_product: [
    { product: 'erp-imobiliario', calls: 2, input_tokens: 2000, output_tokens: 1000, tokens: 3000, credits: 2500, brl: 25,
      pending_calls: 0, per_feature: [
        { feature: 'chat', calls: 1, input_tokens: 1000, output_tokens: 500, tokens: 1500, credits: 1500, brl: 15, pending_calls: 0 },
        { feature: 'resumo', calls: 1, input_tokens: 1000, output_tokens: 500, tokens: 1500, credits: 1000, brl: 10, pending_calls: 0 },
      ] },
    { product: 'social-wiring', calls: 1, input_tokens: 1000, output_tokens: 500, tokens: 1500, credits: 1000, brl: 10,
      pending_calls: 1, per_feature: [
        { feature: 'legenda', calls: 1, input_tokens: 1000, output_tokens: 500, tokens: 1500, credits: 1000, brl: 10, pending_calls: 1 },
      ] },
  ],
  daily: [{ day: '2026-10-28', 'erp-imobiliario': 2500, 'social-wiring': 1000 }],
  products: ['erp-imobiliario', 'social-wiring'],
};
