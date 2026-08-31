/**
 * Wave-2 fix-on-contact regression test for useRecorrentes.ts — the
 * executar mutations were under-invalidating (missing "conta",
 * "orcamento", "relatorios", "patrimonio") despite going through the
 * exact same TransacoesService.criar() path useTransacoes.ts's create
 * mutation does.
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

const EXPECTED = ['recorrentes', 'transacoes', 'contas', 'conta', 'orcamento', 'dashboard', 'relatorios'];

describe('useRecorrentes invalidation (wave-2 fix-on-contact)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('useExecutarPendentes invalidates the full transação-create cascade', async () => {
    mockPost.mockResolvedValue({ data: { executadas: 2, pendentes_processadas: 2, erros: 0 } });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useExecutarPendentes } = await import('@/hooks/useRecorrentes');
    const { result } = renderHook(() => useExecutarPendentes(), { wrapper });

    result.current.mutate();
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const keys = keysInvalidated(invalidateSpy);
    for (const k of EXPECTED) expect(keys).toContainEqual([k]);
    expect(keys).toContainEqual(['patrimonio', 'atual']);
  });

  it('useExecutarUnico invalidates the same cascade', async () => {
    mockPost.mockResolvedValue({ data: { id: 'tx1' } });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useExecutarUnico } = await import('@/hooks/useRecorrentes');
    const { result } = renderHook(() => useExecutarUnico(), { wrapper });

    result.current.mutate('r1');
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const keys = keysInvalidated(invalidateSpy);
    for (const k of EXPECTED) expect(keys).toContainEqual([k]);
    expect(keys).toContainEqual(['patrimonio', 'atual']);
  });
});
