/**
 * useAI hook tests — Tier 1.5 G2 (ai-expansion 2026-04-24).
 *
 * Uses `renderHook` from @testing-library/react with a QueryClientProvider
 * wrapper. Each test stubs `api.post` and asserts the mutation hits the
 * correct URL with the correct payload + parses the response shape.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockPost = vi.fn();

vi.mock('@noctusai/seed/infra', () => ({
  api: { post: mockPost },
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


describe('useAI hooks', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('useFollowUpDraft posts to /api/ai/leads/{id}/follow-up-draft and parses the draft', async () => {
    mockPost.mockResolvedValue({
      data: {
        channel: 'whatsapp',
        subject: null,
        body: 'Olá João',
        days_since_activity: 30,
      },
    });

    const { useFollowUpDraft } = await import('@/hooks/useAI');
    const { result } = renderHook(() => useFollowUpDraft(), { wrapper: withQueryClient() });

    result.current.mutate({ lead_id: 'lead-1', imovel_interesse: 'Apto Centro' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockPost).toHaveBeenCalledWith(
      '/api/ai/leads/lead-1/follow-up-draft',
      { cliente_id: 'lead-1', imovel_interesse: 'Apto Centro' },
    );
    expect(result.current.data?.body).toBe('Olá João');
    expect(result.current.data?.days_since_activity).toBe(30);
  });

  it('useGenerateDescription posts to /api/ai/generate-description', async () => {
    mockPost.mockResolvedValue({
      data: { titulo_sugerido: 'Apto', descricao: 'lindo' },
    });

    const { useGenerateDescription } = await import('@/hooks/useAI');
    const { result } = renderHook(() => useGenerateDescription(), { wrapper: withQueryClient() });

    result.current.mutate({ imovel_id: 'a1' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockPost).toHaveBeenCalledWith('/api/ai/generate-description', { imovel_id: 'a1' });
    expect(result.current.data?.titulo_sugerido).toBe('Apto');
  });

  it('useLeadScore posts to /api/ai/lead-score', async () => {
    mockPost.mockResolvedValue({
      data: { score: 85, justificativa: 'high engagement', recomendacao: 'follow up' },
    });

    const { useLeadScore } = await import('@/hooks/useAI');
    const { result } = renderHook(() => useLeadScore(), { wrapper: withQueryClient() });

    result.current.mutate({ cliente_id: 'c1' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockPost).toHaveBeenCalledWith('/api/ai/lead-score', { cliente_id: 'c1' });
    expect(result.current.data?.score).toBe(85);
  });

  it('useSuggestPrice posts to /api/ai/suggest-price', async () => {
    mockPost.mockResolvedValue({
      data: {
        preco_sugerido: 500000,
        faixa_min: 450000,
        faixa_max: 550000,
        analise: 'baseado em 5 comparáveis',
        total_comparaveis: 5,
      },
    });

    const { useSuggestPrice } = await import('@/hooks/useAI');
    const { result } = renderHook(() => useSuggestPrice(), { wrapper: withQueryClient() });

    result.current.mutate({ imovel_id: 'a1' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockPost).toHaveBeenCalledWith('/api/ai/suggest-price', { imovel_id: 'a1' });
    expect(result.current.data?.preco_sugerido).toBe(500000);
  });
});
