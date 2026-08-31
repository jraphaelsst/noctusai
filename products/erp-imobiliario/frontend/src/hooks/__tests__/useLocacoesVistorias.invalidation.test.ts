/**
 * Wave 2 (cache-invalidation narrowing) — useLocacoes.ts + useVistorias.ts.
 *
 *  - useCreateLocacao / useDeleteLocacao: dropped 'imoveis' — no router
 *    code or DB trigger on contratos_locacao writes back to ativos/imoveis.
 *  - useUpdateLocacao: narrowed the blanket 'locacao' invalidation to the
 *    response's own id.
 *  - useUpdateVistoria / useAddFotosVistoria: same 'vistoria' → id narrowing.
 *  - useCreateVistoria: KEPT 'locacoes' — left broad, unverified cross-
 *    domain link (documented in the hook itself).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockPost = vi.fn();
const mockPatch = vi.fn();
const mockDelete = vi.fn();
const mockAuth = { user: { id: 'u1', email: 'u@test' } };

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
  const wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
  return { wrapper, invalidateSpy };
}

describe('useLocacoes', () => {
  beforeEach(() => vi.clearAllMocks());

  it('useCreateLocacao does NOT invalidate imoveis', async () => {
    mockPost.mockResolvedValue({ data: { id: 'lc1' } });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useCreateLocacao } = await import('@/hooks/useLocacoes');
    const { result } = renderHook(() => useCreateLocacao(), { wrapper });

    result.current.mutate({} as any);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['locacoes'] });
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: ['imoveis'] });
  });

  it('useDeleteLocacao does NOT invalidate imoveis', async () => {
    mockDelete.mockResolvedValue({});
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useDeleteLocacao } = await import('@/hooks/useLocacoes');
    const { result } = renderHook(() => useDeleteLocacao(), { wrapper });

    result.current.mutate('lc1');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['locacoes'] });
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: ['imoveis'] });
  });

  it('useUpdateLocacao narrows locacao invalidation to the id', async () => {
    mockPatch.mockResolvedValue({ data: { id: 'lc1' } });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useUpdateLocacao } = await import('@/hooks/useLocacoes');
    const { result } = renderHook(() => useUpdateLocacao(), { wrapper });

    result.current.mutate({ id: 'lc1' } as any);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['locacao', 'lc1'] });
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: ['locacao'] });
  });
});

describe('useVistorias', () => {
  beforeEach(() => vi.clearAllMocks());

  it('useUpdateVistoria narrows vistoria invalidation to the id', async () => {
    mockPatch.mockResolvedValue({ data: { id: 'v1' } });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useUpdateVistoria } = await import('@/hooks/useVistorias');
    const { result } = renderHook(() => useUpdateVistoria(), { wrapper });

    result.current.mutate({ id: 'v1' } as any);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['vistoria', 'v1'] });
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: ['vistoria'] });
  });

  it('useAddFotosVistoria narrows vistoria invalidation to the id', async () => {
    mockPost.mockResolvedValue({ data: { id: 'v1' } });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useAddFotosVistoria } = await import('@/hooks/useVistorias');
    const { result } = renderHook(() => useAddFotosVistoria(), { wrapper });

    result.current.mutate({ id: 'v1', urls: ['a.jpg'] });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['vistoria', 'v1'] });
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: ['vistoria'] });
  });

  it('useCreateVistoria keeps the locacoes invalidation (documented, left broad)', async () => {
    mockPost.mockResolvedValue({ data: { id: 'v2' } });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useCreateVistoria } = await import('@/hooks/useVistorias');
    const { result } = renderHook(() => useCreateVistoria(), { wrapper });

    result.current.mutate({} as any);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['locacoes'] });
  });
});
