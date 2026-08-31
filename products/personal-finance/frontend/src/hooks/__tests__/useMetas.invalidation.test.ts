/**
 * Wave-2 invalidation-narrowing regression tests for useMetas.ts.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockPatch = vi.fn();
const mockDelete = vi.fn();
const mockPost = vi.fn();

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
  const setDataSpy = vi.spyOn(client, 'setQueryData');
  const removeSpy = vi.spyOn(client, 'removeQueries');
  const wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
  return { wrapper, invalidateSpy, setDataSpy, removeSpy };
}

function keysInvalidated(spy: ReturnType<typeof vi.fn>): unknown[][] {
  return spy.mock.calls.map((c) => (c[0] as { queryKey: unknown[] }).queryKey);
}

describe('useMetas invalidation (wave-2)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('useUpdateMeta patches ["meta", id] directly (fixes MetaDetalhes.tsx not reflecting its own edit) and keeps metas+dashboard', async () => {
    const updated = { id: 'm1', nome: 'Viagem' };
    mockPatch.mockResolvedValue({ data: updated });
    const { wrapper, invalidateSpy, setDataSpy } = makeWrapper();
    const { useUpdateMeta } = await import('@/hooks/useMetas');
    const { result } = renderHook(() => useUpdateMeta(), { wrapper });

    result.current.mutate({ id: 'm1', nome: 'Viagem' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(setDataSpy).toHaveBeenCalledWith(['meta', 'm1'], updated);
    const keys = keysInvalidated(invalidateSpy);
    expect(keys).toContainEqual(['metas']);
    expect(keys).toContainEqual(['dashboard']);
  });

  it('useDeleteMeta purges ["meta", id] and keeps metas+dashboard', async () => {
    mockDelete.mockResolvedValue({});
    const { wrapper, invalidateSpy, removeSpy } = makeWrapper();
    const { useDeleteMeta } = await import('@/hooks/useMetas');
    const { result } = renderHook(() => useDeleteMeta(), { wrapper });

    result.current.mutate('m1');
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(removeSpy).toHaveBeenCalledWith({ queryKey: ['meta', 'm1'] });
    const keys = keysInvalidated(invalidateSpy);
    expect(keys).toContainEqual(['metas']);
    expect(keys).toContainEqual(['dashboard']);
  });

  it('useAddContribuicao keeps metas/meta/dashboard and drops "contas" (adicionar_contribuicao never touches the contas table)', async () => {
    mockPost.mockResolvedValue({ data: { id: 'contrib1' } });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useAddContribuicao } = await import('@/hooks/useMetas');
    const { result } = renderHook(() => useAddContribuicao(), { wrapper });

    result.current.mutate({ id: 'm1', valor: 100 });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const keys = keysInvalidated(invalidateSpy);
    expect(keys).toContainEqual(['metas']);
    expect(keys).toContainEqual(['meta']);
    expect(keys).toContainEqual(['dashboard']);
    expect(keys).not.toContainEqual(['contas']);
  });
});
