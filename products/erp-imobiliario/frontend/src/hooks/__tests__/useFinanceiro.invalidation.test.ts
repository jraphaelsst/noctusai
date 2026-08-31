/**
 * Wave 2 (cache-invalidation narrowing) — useFinanceiro.ts.
 *
 * useUpdateLancamento: narrowed the blanket 'lancamento' invalidation to
 * the response's own id (the list/resumo/fluxo invalidations stay broad —
 * status/categoria/data are filter + aggregation dimensions the edit can
 * move across, and this file's scope was kept shallow per "depth over
 * coverage").
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

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  });
  const invalidateSpy = vi.spyOn(client, 'invalidateQueries');
  const wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
  return { wrapper, invalidateSpy };
}

describe('useUpdateLancamento', () => {
  beforeEach(() => vi.clearAllMocks());

  it('invalidates the specific lancamento id, never the blanket family', async () => {
    mockPatch.mockResolvedValue({ data: { id: 'l1', tipo: 'receita' } });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useUpdateLancamento } = await import('@/hooks/useFinanceiro');
    const { result } = renderHook(() => useUpdateLancamento(), { wrapper });

    result.current.mutate({ id: 'l1', tipo: 'receita' } as any);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['financeiro'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['financeiro-resumo'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['financeiro-fluxo'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['lancamento', 'l1'] });
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: ['lancamento'] });
  });
});
