/**
 * Wave 2 (cache-invalidation narrowing) — usePortais.ts useTogglePortal.
 *
 * `toggle_portal` (backend) is a single-field `UPDATE ativos SET
 * pronto_para_portais = ...` — no other imovel field changes. This mutation
 * used to `invalidateQueries({ queryKey: ['imoveis'] })` on every toggle,
 * force-refetching the WHOLE imoveis list (every property in the org) for
 * one boolean flip. Converted to a targeted `setQueryData` patch (mirrors
 * the pre-existing optimistic patch already applied to
 * `['portais-imoveis', ...]`), with `onError` restoring both caches.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockPatch = vi.fn();
const mockAuth = { user: { id: 'u1', email: 'u@test' } };

vi.mock('@noctusai/seed/infra', () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: mockPatch, delete: vi.fn() },
  useAuthStore: () => mockAuth,
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

function makeClient() {
  return new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  });
}

function wrapperFor(client: QueryClient) {
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
}

describe('useTogglePortal', () => {
  beforeEach(() => vi.clearAllMocks());

  it('patches the imoveis cache directly and never invalidates the root imoveis list', async () => {
    mockPatch.mockResolvedValue({ data: { id: 'im1', pronto_para_portais: true } });
    const client = makeClient();
    client.setQueryData(['imoveis'], [
      { id: 'im1', pronto_para_portais: false },
      { id: 'im2', pronto_para_portais: true },
    ]);
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries');
    const { useTogglePortal } = await import('@/hooks/usePortais');
    const { result } = renderHook(() => useTogglePortal(), { wrapper: wrapperFor(client) });

    result.current.mutate({ imovelId: 'im1', prontoParaPortais: true });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    // Optimistic + confirmed patch — the cache reflects the new value.
    expect(client.getQueryData(['imoveis'])).toEqual([
      { id: 'im1', pronto_para_portais: true },
      { id: 'im2', pronto_para_portais: true },
    ]);
    // The other, untouched row is byte-identical (no full-list refetch).
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: ['imoveis'] });
    // Legitimately-affected aggregates are still refreshed.
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['portais-feeds'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['portais-imoveis'] });
  });

  it('rolls back the imoveis cache on error', async () => {
    mockPatch.mockRejectedValue(new Error('500'));
    const client = makeClient();
    const original = [{ id: 'im1', pronto_para_portais: false }];
    client.setQueryData(['imoveis'], original);
    const { useTogglePortal } = await import('@/hooks/usePortais');
    const { result } = renderHook(() => useTogglePortal(), { wrapper: wrapperFor(client) });

    result.current.mutate({ imovelId: 'im1', prontoParaPortais: true });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(client.getQueryData(['imoveis'])).toEqual(original);
  });
});
