/**
 * Wave-2 invalidation-narrowing regression test for useOperacoes.ts —
 * same cascade as useAtivos.ts; only "patrimonio" narrows to "atual".
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockPost = vi.fn();
const mockDelete = vi.fn();

vi.mock('@noctusai/seed/infra', () => ({
  api: { get: vi.fn(), post: mockPost, patch: vi.fn(), delete: mockDelete },
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

describe('useOperacoes invalidation (wave-2)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('useCreateOperacao and useDeleteOperacao keep the full cascade, narrow patrimonio to "atual"', async () => {
    mockPost.mockResolvedValue({ data: { id: 'op1' } });
    mockDelete.mockResolvedValue({});
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useCreateOperacao, useDeleteOperacao } = await import('@/hooks/useOperacoes');

    const { result: create } = renderHook(() => useCreateOperacao(), { wrapper });
    create.current.mutate({ ticker: 'PETR4', tipo: 'compra' });
    await waitFor(() => expect(create.current.isSuccess).toBe(true));

    const { result: del } = renderHook(() => useDeleteOperacao(), { wrapper });
    del.current.mutate('op1');
    await waitFor(() => expect(del.current.isSuccess).toBe(true));

    const keys = keysInvalidated(invalidateSpy);
    for (const k of ['operacoes', 'ativos', 'carteiras', 'carteira', 'dashboard']) {
      expect(keys.filter((x) => x[0] === k).length).toBeGreaterThanOrEqual(2);
    }
    expect(keys).toContainEqual(['patrimonio', 'atual']);
    expect(keys).not.toContainEqual(['patrimonio']);
  });
});
