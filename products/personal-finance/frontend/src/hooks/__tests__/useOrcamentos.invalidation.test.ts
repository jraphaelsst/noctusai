/**
 * Wave-2 invalidation-narrowing regression tests for useOrcamentos.ts.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockAuth = { user: { id: 'u1', email: 'u@test' } };
const mockPost = vi.fn();
const mockPatch = vi.fn();
const mockDelete = vi.fn();

vi.mock('@noctusai/seed/infra', () => ({
  api: { get: vi.fn(), post: mockPost, patch: mockPatch, delete: mockDelete },
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
  const setDataSpy = vi.spyOn(client, 'setQueryData');
  const removeSpy = vi.spyOn(client, 'removeQueries');
  const wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
  return { wrapper, invalidateSpy, setDataSpy, removeSpy };
}

function keysInvalidated(spy: ReturnType<typeof vi.fn>): unknown[][] {
  return spy.mock.calls.map((c) => (c[0] as { queryKey: unknown[] }).queryKey);
}

describe('useOrcamentos invalidation (wave-2)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('useCreateOrcamento keeps "orcamentos" and drops "dashboard" (DashboardService never reads orcamento data)', async () => {
    mockPost.mockResolvedValue({ data: { id: 'o1', nome: 'Mensal' } });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useCreateOrcamento } = await import('@/hooks/useOrcamentos');
    const { result } = renderHook(() => useCreateOrcamento(), { wrapper });

    result.current.mutate({ nome: 'Mensal' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const keys = keysInvalidated(invalidateSpy);
    expect(keys).toContainEqual(['orcamentos']);
    expect(keys).not.toContainEqual(['dashboard']);
  });

  it('useUpdateOrcamento patches ["orcamento", id] directly and drops "dashboard"', async () => {
    const updated = { id: 'o1', nome: 'Mensal Renamed' };
    mockPatch.mockResolvedValue({ data: updated });
    const { wrapper, invalidateSpy, setDataSpy } = makeWrapper();
    const { useUpdateOrcamento } = await import('@/hooks/useOrcamentos');
    const { result } = renderHook(() => useUpdateOrcamento(), { wrapper });

    result.current.mutate({ id: 'o1', nome: 'Mensal Renamed' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(setDataSpy).toHaveBeenCalledWith(['orcamento', 'o1'], updated);
    const keys = keysInvalidated(invalidateSpy);
    expect(keys).toContainEqual(['orcamentos']);
    expect(keys).not.toContainEqual(['dashboard']);
  });

  it('useDeleteOrcamento purges ["orcamento", id] and drops "dashboard"', async () => {
    mockDelete.mockResolvedValue({});
    const { wrapper, invalidateSpy, removeSpy } = makeWrapper();
    const { useDeleteOrcamento } = await import('@/hooks/useOrcamentos');
    const { result } = renderHook(() => useDeleteOrcamento(), { wrapper });

    result.current.mutate('o1');
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(removeSpy).toHaveBeenCalledWith({ queryKey: ['orcamento', 'o1'] });
    const keys = keysInvalidated(invalidateSpy);
    expect(keys).toContainEqual(['orcamentos']);
    expect(keys).not.toContainEqual(['dashboard']);
  });

  it('useCreateOrcamentoItem keeps only "orcamento" — drops "orcamentos" and "dashboard"', async () => {
    mockPost.mockResolvedValue({ data: { id: 'i1' } });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useCreateOrcamentoItem } = await import('@/hooks/useOrcamentos');
    const { result } = renderHook(() => useCreateOrcamentoItem(), { wrapper });

    result.current.mutate({ orcamentoId: 'o1', categoria_id: 'cat1', valor_planejado: 100, periodo_mes: '2026-08' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const keys = keysInvalidated(invalidateSpy);
    expect(keys).toContainEqual(['orcamento']);
    expect(keys).not.toContainEqual(['orcamentos']);
    expect(keys).not.toContainEqual(['dashboard']);
  });

  it('useUpdateOrcamentoItem and useDeleteOrcamentoItem also keep only "orcamento"', async () => {
    mockPatch.mockResolvedValue({ data: { id: 'i1' } });
    mockDelete.mockResolvedValue({});
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useUpdateOrcamentoItem, useDeleteOrcamentoItem } = await import('@/hooks/useOrcamentos');

    const { result: upd } = renderHook(() => useUpdateOrcamentoItem(), { wrapper });
    upd.current.mutate({ itemId: 'i1', valor_planejado: 200 });
    await waitFor(() => expect(upd.current.isSuccess).toBe(true));

    const { result: del } = renderHook(() => useDeleteOrcamentoItem(), { wrapper });
    del.current.mutate('i1');
    await waitFor(() => expect(del.current.isSuccess).toBe(true));

    const keys = keysInvalidated(invalidateSpy);
    expect(keys.filter((k) => k[0] === 'orcamento').length).toBeGreaterThanOrEqual(2);
    expect(keys).not.toContainEqual(['orcamentos']);
    expect(keys).not.toContainEqual(['dashboard']);
  });
});
