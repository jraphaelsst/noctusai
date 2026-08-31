/**
 * Wave-2 invalidation-narrowing regression tests for useAtivos.ts — the
 * cascade (ativos/carteiras/carteira/dashboard) stays broad on purpose;
 * only "patrimonio" narrows to "atual".
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockPost = vi.fn();
const mockPatch = vi.fn();
const mockDelete = vi.fn();

vi.mock('@noctusai/seed/infra', () => ({
  api: { get: vi.fn(), post: mockPost, patch: mockPatch, delete: mockDelete },
  useAuthStore: () => ({ user: { id: 'u1' } }),
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  });
  const invalidateSpy = vi.spyOn(client, 'invalidateQueries');
  const wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
  return { wrapper, invalidateSpy };
}

function keysInvalidated(spy: ReturnType<typeof vi.fn>): unknown[][] {
  return spy.mock.calls.map((c) => (c[0] as { queryKey: unknown[] }).queryKey);
}

const KEPT_BROAD = ['ativos', 'carteiras', 'carteira', 'dashboard'];

describe('useAtivos invalidation (wave-2)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('useCreateAtivo keeps the full cascade and narrows patrimonio to "atual"', async () => {
    mockPost.mockResolvedValue({ data: { id: 'a1' } });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useCreateAtivo } = await import('@/hooks/useAtivos');
    const { result } = renderHook(() => useCreateAtivo(), { wrapper });

    result.current.mutate({ ticker: 'PETR4' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const keys = keysInvalidated(invalidateSpy);
    for (const k of KEPT_BROAD) expect(keys).toContainEqual([k]);
    expect(keys).toContainEqual(['patrimonio', 'atual']);
    expect(keys).not.toContainEqual(['patrimonio']);
  });

  it('useUpdateAtivo and useDeleteAtivo match the same set', async () => {
    mockPatch.mockResolvedValue({ data: { id: 'a1' } });
    mockDelete.mockResolvedValue({});
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useUpdateAtivo, useDeleteAtivo } = await import('@/hooks/useAtivos');

    const { result: upd } = renderHook(() => useUpdateAtivo(), { wrapper });
    upd.current.mutate({ id: 'a1', quantidade: 10 });
    await waitFor(() => expect(upd.current.isSuccess).toBe(true));

    const { result: del } = renderHook(() => useDeleteAtivo(), { wrapper });
    del.current.mutate('a1');
    await waitFor(() => expect(del.current.isSuccess).toBe(true));

    const keys = keysInvalidated(invalidateSpy);
    for (const k of KEPT_BROAD) {
      expect(keys.filter((x) => x[0] === k).length).toBeGreaterThanOrEqual(2);
    }
    expect(keys).not.toContainEqual(['patrimonio']);
  });
});
