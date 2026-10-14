/** Shared test helpers for the quotes organ (not exported from the barrel). */
import * as React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { makeRoutedApi } from '../organ-kit/testing';
import type { QuotesApi } from './hooks';
import type { QuotePublicView, QuoteRecord } from './types';

export const makeApi = (routes: Record<string, unknown> = {}) => makeRoutedApi<QuotesApi>(routes);

export function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

export function wrapperFor(client: QueryClient = makeClient()) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

export const page = <T,>(rows: T[]) => ({ data: rows, pagination: { page: 1, page_size: 20, total: rows.length } });

export function quote(over: Partial<QuoteRecord> = {}): QuoteRecord {
  return {
    id: 'q1', org_id: 'o', number: 'ORC-00001', root_id: 'q1', version: 1, is_current: true, party_id: 'p1', title: 'Reforma',
    status: 'draft', currency: 'BRL', valid_until: '2026-11-30', notes: null, terms: null, convert_to: null,
    subtotal_cents: 20000, discount_cents: 0, total_cents: 20000, sent_at: null, last_sent_to: null, viewed_at: null,
    accepted_at: null, rejected_at: null, expired_at: null, rejection_reason: null, conversion_status: 'none', conversion_kind: null,
    conversion_ref: null, conversion_error: null, signature_ref: null, signature_status: null, created_at: '2026-10-01T00:00:00Z',
    updated_at: '2026-10-01T00:00:00Z',
    lines: [{ id: 'l1', position: 0, item_id: null, description: 'Instalação', unit: 'UN', kind: 'service', qty: 2, unit_price_cents: 10000, discount_cents: 0, total_cents: 20000 }],
    effective_convert_to: 'contract',
    party: { id: 'p1', legal_name: 'Ana Souza', trade_name: null, email: 'ana@cliente.com' },
    ...over,
  };
}

export function publicView(over: Partial<QuotePublicView> = {}): QuotePublicView {
  return {
    number: 'ORC-00001', version: 1, title: 'Reforma', status: 'viewed', currency: 'BRL', valid_until: '2026-11-30', notes: 'Prazo: 10 dias', terms: '30 dias de garantia',
    subtotal_cents: 20000, discount_cents: 500, total_cents: 19500, party_name: 'Ana Souza', issuer_name: 'Acme Ltda',
    lines: [{ position: 0, description: 'Instalação', unit: 'UN', qty: 2, unit_price_cents: 10000, discount_cents: 0, total_cents: 20000 }],
    can_decide: true, decision: null,
    consent_template: 'Eu, {name}, li e aceito o orçamento ORC-00001 (versão 1), no valor total de R$ 195,00.',
    ...over,
  };
}
