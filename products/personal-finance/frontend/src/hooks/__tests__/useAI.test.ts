/**
 * useAI hook tests — Personal Finance AI features (ai-expansion Phase 7 + Phase 10).
 *
 * Mirrors the canonical pattern from products/erp-imobiliario/frontend/src/hooks/__tests__/useAI.test.ts.
 * Stubs `api.get` and `api.post`, asserts URLs + payloads + parsed shapes.
 *
 * Closes the G2 backlog deferred during ai-expansion Tier 1.5 for Personal Finance.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockGet = vi.fn();
const mockPost = vi.fn();

vi.mock('@noctusai/seed/infra', () => ({
  api: { get: mockGet, post: mockPost },
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


describe('Personal Finance useAI hooks', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('useCategorizeTransaction posts to /api/ai/transacoes/{id}/categorize and returns AIOutput', async () => {
    mockPost.mockResolvedValue({
      data: {
        ref_type: 'transacao',
        ref_id: 'tx-1',
        kind: 'category',
        label: 'Alimentação',
        confidence: 0.92,
        matched_categoria_id: 'cat-food',
      },
    });

    const { useCategorizeTransaction } = await import('@/hooks/useAI');
    const { result } = renderHook(() => useCategorizeTransaction(), { wrapper: withQueryClient() });

    result.current.mutate({ transacao_id: 'tx-1' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockPost).toHaveBeenCalledWith('/api/ai/transacoes/tx-1/categorize', {});
    expect(result.current.data?.label).toBe('Alimentação');
    expect(result.current.data?.matched_categoria_id).toBe('cat-food');
  });

  it('useRecurringFlag posts to /api/ai/transacoes/{id}/recurring-flag and returns AIOutput', async () => {
    mockPost.mockResolvedValue({
      data: {
        ref_type: 'transacao',
        ref_id: 'tx-2',
        kind: 'recurring',
        label: 'Mensal recorrente',
        chip: 'RECORRENTE',
        score: 0.88,
      },
    });

    const { useRecurringFlag } = await import('@/hooks/useAI');
    const { result } = renderHook(() => useRecurringFlag(), { wrapper: withQueryClient() });

    result.current.mutate({ transacao_id: 'tx-2' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockPost).toHaveBeenCalledWith('/api/ai/transacoes/tx-2/recurring-flag', {});
    expect(result.current.data?.chip).toBe('RECORRENTE');
    expect(result.current.data?.score).toBe(0.88);
  });

  it('useMonthlyNarrative gets /api/ai/monthly-narrative and returns response', async () => {
    mockGet.mockResolvedValue({
      data: {
        subject: 'Resumo mensal',
        html: '<p>Mês positivo.</p>',
        text: 'Mês positivo.',
        summary: {
          period_days: 30,
          period_label: 'Abril 2026',
          receita_total: 12000,
          despesa_total: 9500,
          fluxo_liquido: 2500,
          taxa_poupanca: 20.83,
          top_categorias: [
            { nome: 'Alimentação', total: 1800 },
            { nome: 'Transporte', total: 600 },
          ],
          transacoes_count: 87,
          narrative: 'Boa disciplina financeira este mês.',
        },
      },
    });

    const { useMonthlyNarrative } = await import('@/hooks/useAI');
    const { result } = renderHook(() => useMonthlyNarrative(30), { wrapper: withQueryClient() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockGet).toHaveBeenCalledWith('/api/ai/monthly-narrative?period_days=30');
    expect(result.current.data?.summary.fluxo_liquido).toBe(2500);
    expect(result.current.data?.summary.top_categorias).toHaveLength(2);
  });

  it('useMonthlyNarrative threads custom periodDays into URL', async () => {
    mockGet.mockResolvedValue({ data: { subject: 'x', html: '', text: '', summary: { period_days: 7, period_label: '', receita_total: 0, despesa_total: 0, fluxo_liquido: 0, taxa_poupanca: 0, top_categorias: [], transacoes_count: 0, narrative: '' } } });

    const { useMonthlyNarrative } = await import('@/hooks/useAI');
    renderHook(() => useMonthlyNarrative(7), { wrapper: withQueryClient() });

    await waitFor(() => expect(mockGet).toHaveBeenCalled());
    expect(mockGet).toHaveBeenCalledWith('/api/ai/monthly-narrative?period_days=7');
  });
});
