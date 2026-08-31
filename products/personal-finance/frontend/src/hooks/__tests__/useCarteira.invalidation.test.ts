/**
 * Wave-2 invalidation-narrowing regression tests for useCarteira.ts.
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
  const setDataSpy = vi.spyOn(client, 'setQueryData');
  const removeSpy = vi.spyOn(client, 'removeQueries');
  const wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
  return { wrapper, invalidateSpy, setDataSpy, removeSpy };
}

function keysInvalidated(spy: ReturnType<typeof vi.fn>): unknown[][] {
  return spy.mock.calls.map((c) => (c[0] as { queryKey: unknown[] }).queryKey);
}

describe('useCarteira invalidation (wave-2)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('useCreateCarteira keeps only "carteiras" — an empty portfolio cannot move dashboard/patrimonio', async () => {
    mockPost.mockResolvedValue({ data: { id: 'p1', nome: 'Growth' } });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useCreateCarteira } = await import('@/hooks/useCarteira');
    const { result } = renderHook(() => useCreateCarteira(), { wrapper });

    result.current.mutate({ nome: 'Growth' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const keys = keysInvalidated(invalidateSpy);
    expect(keys).toContainEqual(['carteiras']);
    expect(keys).not.toContainEqual(['dashboard']);
    expect(keys).not.toContainEqual(['patrimonio']);
    expect(keys).not.toContainEqual(['patrimonio', 'atual']);
  });

  it('useUpdateCarteira patches ["carteira", id] directly, keeps "carteiras", drops dashboard/patrimonio', async () => {
    const updated = { id: 'p1', nome: 'Growth Renamed' };
    mockPatch.mockResolvedValue({ data: updated });
    const { wrapper, invalidateSpy, setDataSpy } = makeWrapper();
    const { useUpdateCarteira } = await import('@/hooks/useCarteira');
    const { result } = renderHook(() => useUpdateCarteira(), { wrapper });

    result.current.mutate({ id: 'p1', nome: 'Growth Renamed' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(setDataSpy).toHaveBeenCalledWith(['carteira', 'p1'], updated);
    const keys = keysInvalidated(invalidateSpy);
    expect(keys).toContainEqual(['carteiras']);
    expect(keys).not.toContainEqual(['dashboard']);
    expect(keys).not.toContainEqual(['patrimonio', 'atual']);
  });

  it('useDeleteCarteira KEEPS dashboard/patrimonio(atual) — ON DELETE CASCADE removes its ativos — and purges the singular cache', async () => {
    mockDelete.mockResolvedValue({});
    const { wrapper, invalidateSpy, removeSpy } = makeWrapper();
    const { useDeleteCarteira } = await import('@/hooks/useCarteira');
    const { result } = renderHook(() => useDeleteCarteira(), { wrapper });

    result.current.mutate('p1');
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const keys = keysInvalidated(invalidateSpy);
    expect(keys).toContainEqual(['carteiras']);
    expect(keys).toContainEqual(['dashboard']);
    expect(keys).toContainEqual(['patrimonio', 'atual']);
    expect(keys).not.toContainEqual(['patrimonio']);
    expect(removeSpy).toHaveBeenCalledWith({ queryKey: ['carteira', 'p1'] });
  });
});
