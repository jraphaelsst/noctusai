/**
 * useVistaImoveis — key-change flicker regression guard (Category B).
 *
 * `useVistaImoveis`'s `queryKey` includes `page`/`pageSize`/`filters`, so a
 * page or filter change is a KEY change, not a background refetch of the
 * same key — TanStack Query treats it as a brand-new query and `data` goes
 * `undefined` for one tick unless the hook carries `placeholderData`. That
 * blanks the grid every time a user pages or filters (the "key-change
 * flicker" class). This test would have failed against the hook BEFORE
 * `placeholderData: (prev) => prev` was added.
 *
 * Unlike `useVistaClientes` (personal data — see that hook's own doc
 * comment), `useVistaImoveis` is a property listing with no LGPD
 * minimisation concern, so `placeholderData` is the correct default here.
 *
 * Pattern mirrors hooks/__tests__/useVistaClientes.test.ts.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockGet = vi.fn();

vi.mock('@noctusai/seed/infra', () => ({
  api: { get: mockGet, post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  useAuthStore: () => ({ user: { id: 'u1', email: 'u@test' } }),
}));

function withQueryClient() {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
}

const PAGE_1 = {
  pagination: { pagina: 1, quantidade: 1, total: 2, paginas: 2 },
  items: [{ codigo: 'I0001', titulo: 'Apto Centro' }],
};
const PAGE_2 = {
  pagination: { pagina: 2, quantidade: 1, total: 2, paginas: 2 },
  items: [{ codigo: 'I0002', titulo: 'Casa Jardins' }],
};

describe('useVistaImoveis — key-change flicker (Category B)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('keeps the previous page rendered while the next page is still in flight', async () => {
    mockGet.mockResolvedValueOnce(PAGE_1);
    const { useVistaImoveis } = await import('@/hooks/useVistaShowcase');

    const { result, rerender } = renderHook(
      ({ page }: { page: number }) => useVistaImoveis(true, page, 50, {}),
      { wrapper: withQueryClient(), initialProps: { page: 1 } },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items?.[0]?.codigo).toBe('I0001');

    // Page 2 is a queryKey change. Hold the response open so the assertion
    // below runs while the new key's fetch is genuinely in flight — the
    // exact window where `data` goes `undefined` WITHOUT `placeholderData`.
    let resolvePage2!: (v: typeof PAGE_2) => void;
    mockGet.mockReturnValueOnce(new Promise((resolve) => { resolvePage2 = resolve; }));
    rerender({ page: 2 });

    await waitFor(() => expect(result.current.isFetching).toBe(true));
    // The regression this guards: without `placeholderData`, `data` would
    // already be `undefined` here (the grid blanks on every page change).
    expect(result.current.data?.items?.[0]?.codigo).toBe('I0001');

    resolvePage2(PAGE_2);
    await waitFor(() => expect(result.current.data?.items?.[0]?.codigo).toBe('I0002'));
  });
});
