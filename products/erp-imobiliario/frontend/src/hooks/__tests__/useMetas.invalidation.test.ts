/**
 * Wave 2 (cache-invalidation narrowing) — useMetas.ts.
 *
 * The personal goal tracker (`/api/metas`) used to invalidate the literal
 * root key `["metas"]` on every create/update/delete. That root is a
 * TanStack prefix match, so it ALSO invalidated every query in
 * useMetasDomain.ts (equipes/periodos/empresa/regras/config/rankings/
 * fechamentos — the team/gamification cascade), which shares nothing with
 * the personal tracker (see useMetas.ts's METAS_ROOT docblock). Renamed the
 * root to "metas-pessoais" to remove the collision. These tests assert the
 * NEW root is invalidated and the OLD root is not.
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

describe('useMetas — invalidation scoped to metas-pessoais', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('useCreateMeta invalidates metas-pessoais, never the bare "metas" root', async () => {
    mockPost.mockResolvedValue({ data: { id: 'm1' } });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useCreateMeta } = await import('@/hooks/useMetas');
    const { result } = renderHook(() => useCreateMeta(), { wrapper });

    result.current.mutate({} as any);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['metas-pessoais'] });
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: ['metas'] });
  });

  it('useUpdateMeta invalidates metas-pessoais, never the bare "metas" root', async () => {
    mockPatch.mockResolvedValue({ data: { id: 'm1' } });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useUpdateMeta } = await import('@/hooks/useMetas');
    const { result } = renderHook(() => useUpdateMeta(), { wrapper });

    result.current.mutate({ id: 'm1' } as any);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['metas-pessoais'] });
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: ['metas'] });
  });

  it('useDeleteMeta invalidates metas-pessoais, never the bare "metas" root', async () => {
    mockDelete.mockResolvedValue({});
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useDeleteMeta } = await import('@/hooks/useMetas');
    const { result } = renderHook(() => useDeleteMeta(), { wrapper });

    result.current.mutate('m1');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['metas-pessoais'] });
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: ['metas'] });
  });

  it('the useMetas() list query itself keys off metas-pessoais', async () => {
    const { api } = await import('@noctusai/seed/infra');
    (api.get as any).mockResolvedValue({ data: [] });
    const client = new QueryClient({
      defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
    });
    const wrapper = ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client }, children);
    const { useMetas } = await import('@/hooks/useMetas');
    const { result } = renderHook(() => useMetas(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(client.getQueryData(['metas-pessoais', undefined])).toEqual([]);
  });
});

describe('sibling mutation files also target metas-pessoais (not the team/gamification "metas" root)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('useCriarMetaHoje', async () => {
    mockPost.mockResolvedValue({ data: { message: 'ok', metas_criadas: 1 } });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useCriarMetaHoje } = await import('@/hooks/useCriarMetaHoje');
    const { result } = renderHook(() => useCriarMetaHoje(), { wrapper });

    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['metas-pessoais'] });
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: ['metas'] });
  });

  it('useConcluirMetaAgrupada', async () => {
    mockPost.mockResolvedValue({ data: { success: true } });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useConcluirMetaAgrupada } = await import('@/hooks/useConcluirMetaAgrupada');
    const { result } = renderHook(() => useConcluirMetaAgrupada(), { wrapper });

    result.current.mutate('m1');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['metas-pessoais'] });
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: ['metas'] });
  });

  it('useAtualizarStatusMetas', async () => {
    mockPost.mockResolvedValue({ data: { metas_atualizadas: 3 } });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useAtualizarStatusMetas } = await import('@/hooks/useAtualizarStatusMetas');
    const { result } = renderHook(() => useAtualizarStatusMetas(), { wrapper });

    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['metas-pessoais'] });
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: ['metas'] });
  });

  it('useUpsertMetaConfig invalidates both metas-config and metas-pessoais (criar-hoje side effect)', async () => {
    mockPost.mockResolvedValue({ data: { id: 'c1' } });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useUpsertMetaConfig } = await import('@/hooks/useMetasConfig');
    const { result } = renderHook(() => useUpsertMetaConfig(), { wrapper });

    result.current.mutate({ categoria: 'captacao', meta_pretendida: 5, ativo: true } as any);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['metas-config'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['metas-pessoais'] });
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: ['metas'] });
  });
});
