/**
 * Wave-2 invalidation-narrowing regression tests for useContas.ts.
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
  return { client, wrapper, invalidateSpy, setDataSpy, removeSpy };
}

function keysInvalidated(spy: ReturnType<typeof vi.fn>): unknown[][] {
  return spy.mock.calls.map((c) => (c[0] as { queryKey: unknown[] }).queryKey);
}

describe('useContas invalidation (wave-2)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('useCreateConta keeps contas/dashboard and narrows patrimonio to "atual"', async () => {
    mockPost.mockResolvedValue({ data: { id: 'c1', saldo: 0 } });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useCreateConta } = await import('@/hooks/useContas');
    const { result } = renderHook(() => useCreateConta(), { wrapper });

    result.current.mutate({ nome: 'Nubank' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const keys = keysInvalidated(invalidateSpy);
    expect(keys).toContainEqual(['contas']);
    expect(keys).toContainEqual(['dashboard']);
    expect(keys).toContainEqual(['patrimonio', 'atual']);
    expect(keys).not.toContainEqual(['patrimonio']);
  });

  it('useUpdateConta patches ["conta", id] directly with the response and still invalidates the list', async () => {
    const updated = { id: 'c1', nome: 'Nubank Renamed', saldo: 500 };
    mockPatch.mockResolvedValue({ data: updated });
    const { wrapper, invalidateSpy, setDataSpy } = makeWrapper();
    const { useUpdateConta } = await import('@/hooks/useContas');
    const { result } = renderHook(() => useUpdateConta(), { wrapper });

    result.current.mutate({ id: 'c1', nome: 'Nubank Renamed' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    // The single-account cache is patched directly, not invalidated —
    // this is the fix for ContaDetalhes.tsx not reflecting its own edit.
    expect(setDataSpy).toHaveBeenCalledWith(['conta', 'c1'], updated);

    const keys = keysInvalidated(invalidateSpy);
    expect(keys).toContainEqual(['contas']);
    expect(keys).toContainEqual(['dashboard']);
    expect(keys).toContainEqual(['patrimonio', 'atual']);
  });

  it('useDeleteConta purges ["conta", id] instead of invalidating a now-404 resource', async () => {
    mockDelete.mockResolvedValue({});
    const { wrapper, invalidateSpy, removeSpy } = makeWrapper();
    const { useDeleteConta } = await import('@/hooks/useContas');
    const { result } = renderHook(() => useDeleteConta(), { wrapper });

    result.current.mutate('c1');
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(removeSpy).toHaveBeenCalledWith({ queryKey: ['conta', 'c1'] });
    const keys = keysInvalidated(invalidateSpy);
    expect(keys).toContainEqual(['contas']);
    expect(keys).toContainEqual(['dashboard']);
    expect(keys).toContainEqual(['patrimonio', 'atual']);
  });
});
