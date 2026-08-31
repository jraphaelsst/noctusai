/**
 * Wave-2 invalidation-narrowing regression test for useCategorias.ts —
 * the "orcamentos" → "orcamento" wrong-key fix on useUpdateCategoria.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockAuth = { user: { id: 'u1', email: 'u@test' } };
const mockPatch = vi.fn();

vi.mock('@noctusai/seed/infra', () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: mockPatch, delete: vi.fn() },
  useAuthStore: () => mockAuth,
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

describe('useCategorias invalidation (wave-2)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('useUpdateCategoria keeps categorias + transacoes and targets "orcamento" (not the wrong-key "orcamentos")', async () => {
    mockPatch.mockResolvedValue({ data: { id: 'cat1', nome: 'Mercado' } });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useUpdateCategoria } = await import('@/hooks/useCategorias');
    const { result } = renderHook(() => useUpdateCategoria(), { wrapper });

    result.current.mutate({ id: 'cat1', nome: 'Mercado' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const keys = keysInvalidated(invalidateSpy);
    expect(keys).toContainEqual(['categorias']);
    expect(keys).toContainEqual(['transacoes']);
    expect(keys).toContainEqual(['orcamento']);
    expect(keys).not.toContainEqual(['orcamentos']);
  });
});
