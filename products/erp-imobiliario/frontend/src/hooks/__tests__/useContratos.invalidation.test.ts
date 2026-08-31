/**
 * Wave 2 (cache-invalidation narrowing) — useContratos.ts.
 *
 *  - useUpdateContrato: dropped 'parcelas' (a contrato PATCH never writes
 *    parcelas_contrato) and narrowed the blanket 'contrato' invalidation to
 *    the response's own id.
 *  - useGerarParcelas: dropped 'financeiro'/'financeiro-resumo' (the
 *    ledger never reads parcelas_contrato) and ADDED 'contratos-resumo'
 *    (pre-existing gap: regenerating parcelas can change the resumo's
 *    inadimplencia count).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();
const mockDelete = vi.fn();
const mockAuth = { user: { id: 'u1', email: 'u@test' } };

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

describe('useUpdateContrato', () => {
  beforeEach(() => vi.clearAllMocks());

  it('invalidates contratos, contratos-resumo and the specific contrato id — never parcelas', async () => {
    mockPatch.mockResolvedValue({ data: { id: 'c1', status: 'ativo' } });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useUpdateContrato } = await import('@/hooks/useContratos');
    const { result } = renderHook(() => useUpdateContrato(), { wrapper });

    result.current.mutate({ id: 'c1', status: 'ativo' } as any);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['contratos'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['contratos-resumo'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['contrato', 'c1'] });
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: ['contrato'] });
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: ['parcelas'] });
  });
});

describe('useGerarParcelas', () => {
  beforeEach(() => vi.clearAllMocks());

  it('invalidates parcelas, contratos and contratos-resumo — never the financeiro ledger', async () => {
    mockPost.mockResolvedValue({ data: [{ id: 'p1' }] });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useGerarParcelas } = await import('@/hooks/useContratos');
    const { result } = renderHook(() => useGerarParcelas(), { wrapper });

    result.current.mutate({ contratoId: 'c1', valor_entrada: 1000, num_parcelas: 12 });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['parcelas'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['contratos'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['contratos-resumo'] });
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: ['financeiro'] });
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: ['financeiro-resumo'] });
  });
});
