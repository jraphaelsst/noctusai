/**
 * Corretor-tier hook golden-path smoke tests — Phase 5 (erp-wiring 2026-05-20).
 *
 * One smoke test per corretor-surface hook:
 *   useAtividades / useFunil / useDistribuicaoConfig / useEventos /
 *   useCheckins / useComissoes / useCampanhas / useDashboardResumo
 *
 * Pattern mirrors hooks/__tests__/useAI.test.ts (Tier 1.5 G2).
 *
 * Goal: verify each hook calls the correct backend path with the expected
 * query/body shape and surfaces the parsed `data` field. Detail/mutation
 * variants of these surfaces are exercised by the backend router tests
 * (tests/routers/test_<surface>_router.py — 133 tests across the 8 routers).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockAuth = { user: { id: 'u1', email: 'u@test' } };

vi.mock('@noctusai/seed/infra', () => ({
  api: { get: mockGet, post: mockPost, patch: vi.fn(), delete: vi.fn() },
  useAuthStore: () => mockAuth,
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));


function withQueryClient() {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
}


describe('Corretor-tier hook smoke tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('useAtividades fetches /api/atividates with cliente_id filter', async () => {
    mockGet.mockResolvedValue({ data: [{ id: 'a1', descricao: 'call' }] });
    const { useAtividades } = await import('@/hooks/useAtividades');
    const { result } = renderHook(() => useAtividades('c1'), { wrapper: withQueryClient() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith('/api/atividades', { cliente_id: 'c1' });
    expect(result.current.data).toEqual([{ id: 'a1', descricao: 'call' }]);
  });

  it('useFunil fetches /api/funil with provided filters', async () => {
    mockGet.mockResolvedValue({
      data: [{ etapa: 'qualificacao', total: 0, valorTotal: 0, cards: [] }],
    });
    const { useFunil } = await import('@/hooks/useFunil');
    const { result } = renderHook(() => useFunil({ busca: 'joão', responsavelId: 'r1' }), {
      wrapper: withQueryClient(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith('/api/funil', expect.objectContaining({
      busca: 'joão',
      responsavel_id: 'r1',
    }));
    expect(result.current.data?.[0].etapa).toBe('qualificacao');
  });

  it('useDistribuicaoConfig fetches /api/distribuicao/config', async () => {
    mockGet.mockResolvedValue({ data: { round_robin: true } });
    const { useDistribuicaoConfig } = await import('@/hooks/useDistribuicao');
    const { result } = renderHook(() => useDistribuicaoConfig(), { wrapper: withQueryClient() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith('/api/distribuicao/config');
    expect(result.current.data).toEqual({ round_robin: true });
  });

  it('useEventos fetches /api/agenda with filtros', async () => {
    mockGet.mockResolvedValue({ data: [{ id: 'e1', titulo: 'Visita' }], pagination: null });
    const { useEventos } = await import('@/hooks/useAgenda');
    const { result } = renderHook(() => useEventos({ corretor_id: 'u1' }), {
      wrapper: withQueryClient(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith('/api/agenda', expect.objectContaining({ corretor_id: 'u1' }));
    expect(result.current.data?.data?.[0].id).toBe('e1');
  });

  it('useCheckins fetches /api/campo/checkins', async () => {
    mockGet.mockResolvedValue({ data: [{ id: 'ck1', latitude: -23.5 }] });
    const { useCheckins } = await import('@/hooks/useCampo');
    const { result } = renderHook(() => useCheckins({ corretor_id: 'u1' }), {
      wrapper: withQueryClient(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith('/api/campo/checkins', { corretor_id: 'u1' });
    expect(result.current.data?.[0].id).toBe('ck1');
  });

  it('useComissoes fetches /api/comissoes with filtros', async () => {
    mockGet.mockResolvedValue({ data: [{ id: 'co1', valor: 1000 }], pagination: null });
    const { useComissoes } = await import('@/hooks/useComissoes');
    const { result } = renderHook(() => useComissoes({ status: 'pendente' }), {
      wrapper: withQueryClient(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith('/api/comissoes', expect.objectContaining({ status: 'pendente' }));
    expect(result.current.data?.data?.[0].valor).toBe(1000);
  });

  it('useCampanhas fetches /api/marketing/campanhas', async () => {
    mockGet.mockResolvedValue({ data: [{ id: 'cp1', nome: 'Campanha Q1' }], pagination: null });
    const { useCampanhas } = await import('@/hooks/useMarketing');
    const { result } = renderHook(() => useCampanhas({ status: 'ativa' }), {
      wrapper: withQueryClient(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith('/api/marketing/campanhas', expect.objectContaining({ status: 'ativa' }));
    expect(result.current.data?.data?.[0].id).toBe('cp1');
  });

  it('useDashboardResumo fetches /api/bi/dashboard', async () => {
    mockGet.mockResolvedValue({
      data: { vendas_mes: 5, captacao_mes: 12, comissoes_total: 50000 },
    });
    const { useDashboardResumo } = await import('@/hooks/useBI');
    const { result } = renderHook(() => useDashboardResumo(), { wrapper: withQueryClient() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith('/api/bi/dashboard');
    expect(result.current.data?.vendas_mes).toBe(5);
  });
});
