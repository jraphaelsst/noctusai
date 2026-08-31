/**
 * useAdminTherapists placeholderData regression test — the "key-change
 * flicker" this slice fixes fleet-wide (`fleet-placeholder-data`).
 *
 * Before the fix: `useQuery({ queryKey: KEYS.therapists(filters), ... })`
 * had no `placeholderData`, so the moment `filters` changed, TanStack Query
 * treated it as a brand-new query — `data` went `undefined` and the admin
 * therapists table blanked before the new page landed.
 *
 * This test changes `filters` mid-flight (before the second fetch
 * resolves) and asserts the PREVIOUS page's data is still on `result.
 * current.data` during the transition, with `isPlaceholderData: true`
 * marking it as such — never a bare `undefined`. Without `placeholderData:
 * (prev) => prev` on the hook, this test fails (`data` goes `undefined`
 * the instant `filters` changes).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockGet = vi.fn();

vi.mock('@noctusai/seed/infra', () => ({
  api: { get: mockGet, post: vi.fn() },
  useAuthStore: () => ({ user: { id: 'admin-test' } }),
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

function withQueryClient() {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
}

describe('useAdminTherapists placeholderData (key-change flicker)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('keeps the previous page visible (never undefined) while a filter change is in flight', async () => {
    const { useAdminTherapists } = await import('@/hooks/useAdmin');

    // First page resolves immediately.
    mockGet.mockResolvedValueOnce({ data: [{ id: 't1', nome: 'Terapeuta A' }], total: 1 });

    const { result, rerender } = renderHook(
      ({ filters }: { filters?: Record<string, string> }) => useAdminTherapists(filters),
      { wrapper: withQueryClient(), initialProps: { filters: undefined } },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual({ data: [{ id: 't1', nome: 'Terapeuta A' }], total: 1 });

    // Second fetch (triggered by the filter change below) is held open —
    // this is the transition window where the flicker used to happen.
    let resolveSecond!: (v: unknown) => void;
    mockGet.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveSecond = resolve;
      }),
    );

    rerender({ filters: { specialty: 'ansiedade' } });

    // Mid-flight: the query key changed (a new fetch is in progress) but
    // `data` must still be the PREVIOUS page, not undefined — this is the
    // assertion that fails without `placeholderData: (prev) => prev`.
    expect(result.current.isFetching).toBe(true);
    expect(result.current.data).toEqual({ data: [{ id: 't1', nome: 'Terapeuta A' }], total: 1 });
    expect(result.current.isPlaceholderData).toBe(true);

    // Resolve the second fetch — data now updates to the new page.
    resolveSecond({ data: [{ id: 't2', nome: 'Terapeuta B' }], total: 1 });
    await waitFor(() => expect(result.current.isPlaceholderData).toBe(false));
    expect(result.current.data).toEqual({ data: [{ id: 't2', nome: 'Terapeuta B' }], total: 1 });
  });
});
