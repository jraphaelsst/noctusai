/**
 * Wave-2 invalidation-narrowing regression tests for useTransacoes.ts.
 *
 * The important half is the KEPT-keys assertion (per the wave-2 brief):
 * it is what catches an over-narrowing regression landing later. The
 * dropped/wrong-key assertions cover what this wave actually fixed.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockAuth = { user: { id: 'u1', email: 'u@test' } };
const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();
const mockDelete = vi.fn();

vi.mock('@noctusai/seed/infra', () => ({
  api: { get: mockGet, post: mockPost, patch: mockPatch, delete: mockDelete },
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

describe('useTransacoes invalidation (wave-2)', () => {
  beforeEach(() => vi.clearAllMocks());

  const KEPT = ['transacoes', 'contas', 'conta', 'orcamento', 'dashboard', 'relatorios'];

  it('useCreateTransacao keeps the full affected set, narrows patrimonio to ["patrimonio","atual"], and never touches "orcamentos"', async () => {
    mockPost.mockResolvedValue({ data: { id: 't1', conta_id: 'c1' } });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useCreateTransacao } = await import('@/hooks/useTransacoes');
    const { result } = renderHook(() => useCreateTransacao(), { wrapper });

    result.current.mutate({ conta_id: 'c1', valor: 10, tipo: 'despesa' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const keys = keysInvalidated(invalidateSpy);
    for (const k of KEPT) {
      expect(keys).toContainEqual([k]);
    }
    expect(keys).toContainEqual(['patrimonio', 'atual']);
    // Wrong-key bug fixed: the plain budget LIST root must never be hit —
    // only the "orcamento" family (progresso) actually changes.
    expect(keys).not.toContainEqual(['orcamentos']);
    // Narrowed: "historico" (immutable snapshot rows) must not refetch.
    expect(keys).not.toContainEqual(['patrimonio']);
    expect(keys).not.toContainEqual(['patrimonio', 'historico']);
  });

  it('useUpdateTransacao keeps the same set as create', async () => {
    mockPatch.mockResolvedValue({ data: { id: 't1', conta_id: 'c1' } });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useUpdateTransacao } = await import('@/hooks/useTransacoes');
    const { result } = renderHook(() => useUpdateTransacao(), { wrapper });

    result.current.mutate({ id: 't1', valor: 20 });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const keys = keysInvalidated(invalidateSpy);
    for (const k of KEPT) {
      expect(keys).toContainEqual([k]);
    }
    expect(keys).toContainEqual(['patrimonio', 'atual']);
    expect(keys).not.toContainEqual(['orcamentos']);
  });

  it('useDeleteTransacao keeps the same set (root-level — the deleted row does not tell us which conta_id was affected)', async () => {
    mockDelete.mockResolvedValue({});
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useDeleteTransacao } = await import('@/hooks/useTransacoes');
    const { result } = renderHook(() => useDeleteTransacao(), { wrapper });

    result.current.mutate('t1');
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const keys = keysInvalidated(invalidateSpy);
    for (const k of KEPT) {
      expect(keys).toContainEqual([k]);
    }
    expect(keys).toContainEqual(['patrimonio', 'atual']);
    expect(keys).not.toContainEqual(['orcamentos']);
  });
});
