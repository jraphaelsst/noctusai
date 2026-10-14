/** Shared test helpers for the parties organ (not exported from the barrel). */
import * as React from 'react';
import { vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PartiesApi } from './hooks';
import type { Party } from './types';

export const VALID_CPF = '529.982.247-25';
export const VALID_CNPJ = '11.222.333/0001-81';

export function makeApi(overrides: Partial<Record<keyof PartiesApi, unknown>> = {}) {
  return {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    upload: vi.fn(),
    download: vi.fn(),
    ...overrides,
  } as unknown as { [K in keyof PartiesApi]: ReturnType<typeof vi.fn> } & PartiesApi;
}

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

export function party(over: Partial<Party> = {}): Party {
  return {
    id: 'p1',
    org_id: 'org',
    kind: 'PF',
    doc: '52998224725',
    legal_name: 'Ana Souza',
    trade_name: null,
    email: 'ana@x.com',
    phones: ['+5511994573387'],
    address: {},
    state_registration: null,
    municipal_registration: null,
    notes: null,
    is_active: true,
    roles: ['customer'],
    created_at: '2026-10-01T00:00:00Z',
    updated_at: '2026-10-01T00:00:00Z',
    ...over,
  };
}
