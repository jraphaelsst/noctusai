/**
 * Wave-2 invalidation-narrowing regression test for useCotacoes.ts.
 *
 * This mutation is one of the deliberate LEAVE-BROAD cases: a price
 * refresh legitimately touches every ativo/carteira in the org. Only
 * "patrimonio" narrows to "atual" (the one key with a real, immutable
 * "historico" sibling that cannot be affected).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockPost = vi.fn();

vi.mock('@noctusai/seed/infra', () => ({
  api: { get: vi.fn(), post: mockPost, patch: vi.fn(), delete: vi.fn() },
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

describe('useCotacoes invalidation (wave-2)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('useAtualizarPrecos keeps cotacao/ativos/carteiras/carteira/dashboard broad and narrows only patrimonio', async () => {
    mockPost.mockResolvedValue({ data: { atualizado: 5 } });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useAtualizarPrecos } = await import('@/hooks/useCotacoes');
    const { result } = renderHook(() => useAtualizarPrecos(), { wrapper });

    result.current.mutate();
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const keys = keysInvalidated(invalidateSpy);
    for (const k of ['cotacao', 'ativos', 'carteiras', 'carteira', 'dashboard']) {
      expect(keys).toContainEqual([k]);
    }
    expect(keys).toContainEqual(['patrimonio', 'atual']);
    expect(keys).not.toContainEqual(['patrimonio']);
  });
});
