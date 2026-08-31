/**
 * Wave 2 (cache-invalidation narrowing) — useMetasDomain.ts, the team/
 * gamification "metas" cluster (equipes/periodos/empresa/regras/config/
 * rankings/fechamentos), the single worst cluster in the fleet audit.
 *
 * Covers:
 *  - useAdicionarMembro / useRemoverMembro: dropped the blanket
 *    ['metas','equipes'] invalidation — `equipes_service.adicionar_membro`/
 *    `remover_membro` never write the `equipes` table (bare `select("*")`
 *    with no membro-count column).
 *  - useUpsertMetaEmpresa: ADDED ['metas','empresa-resumo'] — a
 *    pre-existing gap (fix-on-contact), since `resumo_cascata` derives
 *    `meta_empresa`/`saldo_a_alocar` live off the same row this writes.
 *  - useUpsertConfig: ADDED ['metas','rankings'] — another pre-existing
 *    gap, since `compute_rankings` folds vgv_por_ponto/peso_pontos/
 *    peso_vgv straight into score_unificado on every call.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();
const mockPut = vi.fn();
const mockDelete = vi.fn();
const mockAuth = { user: { id: 'u1', email: 'u@test' } };

vi.mock('@noctusai/seed/infra', () => ({
  api: { get: mockGet, post: mockPost, patch: mockPatch, put: mockPut, delete: mockDelete },
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

describe('useMetasDomain — equipe-membros mutations no longer touch the equipes list', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('useAdicionarMembro invalidates equipe-membros only', async () => {
    mockPost.mockResolvedValue({ data: { id: 'mb1' } });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useAdicionarMembro } = await import('@/hooks/useMetasDomain');
    const { result } = renderHook(() => useAdicionarMembro('eq1'), { wrapper });

    result.current.mutate({ user_id: 'u2' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['metas', 'equipe-membros', 'eq1'] });
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: ['metas', 'equipes'] });
  });

  it('useRemoverMembro invalidates equipe-membros only', async () => {
    mockDelete.mockResolvedValue({ data: {} });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useRemoverMembro } = await import('@/hooks/useMetasDomain');
    const { result } = renderHook(() => useRemoverMembro('eq1'), { wrapper });

    result.current.mutate('mb1');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['metas', 'equipe-membros', 'eq1'] });
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: ['metas', 'equipes'] });
  });

  it('useCriarEquipe (control) still invalidates the equipes list it actually changes', async () => {
    mockPost.mockResolvedValue({ data: { id: 'eq2' } });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useCriarEquipe } = await import('@/hooks/useMetasDomain');
    const { result } = renderHook(() => useCriarEquipe(), { wrapper });

    result.current.mutate({ nome: 'Equipe X' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['metas', 'equipes'] });
  });
});

describe('useMetasDomain — pre-existing under-invalidation gaps fixed in-flight', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('useUpsertMetaEmpresa invalidates both empresa and empresa-resumo', async () => {
    mockPost.mockResolvedValue({ data: { id: 'me1' } });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useUpsertMetaEmpresa } = await import('@/hooks/useMetasDomain');
    const { result } = renderHook(() => useUpsertMetaEmpresa(), { wrapper });

    result.current.mutate({ periodo_id: 'p1', valor_meta: 100 });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['metas', 'empresa'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['metas', 'empresa-resumo'] });
  });

  it('useUpsertConfig invalidates both config and rankings', async () => {
    mockPut.mockResolvedValue({ data: { org_id: 'o1' } });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useUpsertConfig } = await import('@/hooks/useMetasDomain');
    const { result } = renderHook(() => useUpsertConfig(), { wrapper });

    result.current.mutate({ peso_pontos: 2 });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['metas', 'config'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['metas', 'rankings'] });
  });
});
