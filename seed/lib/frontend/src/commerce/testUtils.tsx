/** Shared test helpers for the commerce organ (not exported from the barrel). */
import * as React from 'react';
import { vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { CommerceApi } from './hooks';

export const VALID_CNPJ = '11.222.333/0001-81';
export const VALID_CPF = '529.982.247-25';

export function makeApi(overrides: Partial<Record<keyof CommerceApi, unknown>> = {}) {
  return {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    upload: vi.fn(),
    ...overrides,
  } as unknown as { [K in keyof CommerceApi]: ReturnType<typeof vi.fn> } & CommerceApi;
}

export function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

export function wrapperFor(client: QueryClient = makeClient()) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}
