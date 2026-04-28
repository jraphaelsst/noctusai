/**
 * useAI hook tests — Mailing AI features (ai-expansion Phase 8 + Phase 14).
 *
 * Mirrors the canonical pattern from products/erp-imobiliario/frontend/src/hooks/__tests__/useAI.test.ts:
 * `renderHook` from @testing-library/react with a QueryClientProvider wrapper;
 * each test stubs `api.post` and asserts the mutation hits the correct URL with
 * the correct payload + parses the response shape. No real network.
 *
 * Closes the G2 backlog deferred during ai-expansion Tier 1.5 (frontend hook
 * tests for the 5 Phase-14 hooks + the M3 segmentation hook).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockPost = vi.fn();

vi.mock('@noctusai/seed/infra', () => ({
  api: { post: mockPost },
}));


function withQueryClient() {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
}


describe('Mailing useAI hooks', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('useGenerateSubjects posts to /api/ai/subjects and returns variants', async () => {
    mockPost.mockResolvedValue({
      data: {
        variants: [
          { text: 'Black Friday: até 50% off', tone: 'urgent' },
          { text: 'Confira nossas ofertas', tone: 'neutral' },
        ],
      },
    });

    const { useGenerateSubjects } = await import('@/hooks/useAI');
    const { result } = renderHook(() => useGenerateSubjects(), { wrapper: withQueryClient() });

    result.current.mutate({ campaign_summary: 'Black Friday B2B' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockPost).toHaveBeenCalledWith('/api/ai/subjects', { campaign_summary: 'Black Friday B2B' });
    expect(result.current.data).toHaveLength(2);
    expect(result.current.data?.[0].text).toBe('Black Friday: até 50% off');
  });

  it('useGenerateSubjects returns [] when response has no variants', async () => {
    mockPost.mockResolvedValue({ data: {} });

    const { useGenerateSubjects } = await import('@/hooks/useAI');
    const { result } = renderHook(() => useGenerateSubjects(), { wrapper: withQueryClient() });

    result.current.mutate({ campaign_summary: 'x' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual([]);
  });

  it('useDraftTemplate posts to /api/ai/template-draft and returns html', async () => {
    mockPost.mockResolvedValue({ data: { html: '<h1>Olá</h1>' } });

    const { useDraftTemplate } = await import('@/hooks/useAI');
    const { result } = renderHook(() => useDraftTemplate(), { wrapper: withQueryClient() });

    result.current.mutate({ prompt: 'Bem-vindo ao Noctus' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockPost).toHaveBeenCalledWith('/api/ai/template-draft', { prompt: 'Bem-vindo ao Noctus' });
    expect(result.current.data).toBe('<h1>Olá</h1>');
  });

  it('useReengagementVariants posts to /api/ai/reengagement and returns variants', async () => {
    mockPost.mockResolvedValue({
      data: {
        variants: [
          { tone: 'gentle', subject: 'Sentimos sua falta', body_html: '<p>Olá</p>' },
          { tone: 'direct', subject: 'Volte hoje', body_html: '<p>Hey</p>' },
        ],
      },
    });

    const { useReengagementVariants } = await import('@/hooks/useAI');
    const { result } = renderHook(() => useReengagementVariants(), { wrapper: withQueryClient() });

    result.current.mutate({ context: 'inativos 60d' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockPost).toHaveBeenCalledWith('/api/ai/reengagement', { context: 'inativos 60d' });
    expect(result.current.data).toHaveLength(2);
    expect(result.current.data?.[1].tone).toBe('direct');
  });

  it('useDeliverabilityReview posts to /api/ai/deliverability and wraps findings', async () => {
    mockPost.mockResolvedValue({
      data: {
        findings: [
          { code: 'spam_words', severity: 'warning', message: 'Evite "GRÁTIS" no assunto' },
        ],
      },
    });

    const { useDeliverabilityReview } = await import('@/hooks/useAI');
    const { result } = renderHook(() => useDeliverabilityReview(), { wrapper: withQueryClient() });

    result.current.mutate({ html: '<p>x</p>', subject: 'GRÁTIS!' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockPost).toHaveBeenCalledWith('/api/ai/deliverability', { html: '<p>x</p>', subject: 'GRÁTIS!' });
    expect(result.current.data?.findings[0].severity).toBe('warning');
  });

  it('useTranslateTemplate posts to /api/ai/translate and returns translated html', async () => {
    mockPost.mockResolvedValue({ data: { html: '<h1>Hello</h1>' } });

    const { useTranslateTemplate } = await import('@/hooks/useAI');
    const { result } = renderHook(() => useTranslateTemplate(), { wrapper: withQueryClient() });

    result.current.mutate({ html: '<h1>Olá</h1>', target_lang: 'en' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockPost).toHaveBeenCalledWith('/api/ai/translate', { html: '<h1>Olá</h1>', target_lang: 'en' });
    expect(result.current.data).toBe('<h1>Hello</h1>');
  });

  it('useTranslateTemplate falls back to original html when response missing', async () => {
    mockPost.mockResolvedValue({ data: {} });

    const { useTranslateTemplate } = await import('@/hooks/useAI');
    const { result } = renderHook(() => useTranslateTemplate(), { wrapper: withQueryClient() });

    result.current.mutate({ html: '<p>fallback</p>', target_lang: 'es' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toBe('<p>fallback</p>');
  });

  it('useSegmentContacts posts to /api/ai/segment-contacts and returns SegmentResult', async () => {
    mockPost.mockResolvedValue({
      data: {
        segmented: 12,
        persisted: [
          { ref_type: 'contact', ref_id: 'c1', label: 'High value', chip: 'VIP' },
          { ref_type: 'contact', ref_id: 'c2', label: 'Cold', chip: 'COLD' },
        ],
      },
    });

    const { useSegmentContacts } = await import('@/hooks/useAI');
    const { result } = renderHook(() => useSegmentContacts(), { wrapper: withQueryClient() });

    result.current.mutate({ list_id: 'list-1', threshold: 0.78 });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockPost).toHaveBeenCalledWith('/api/ai/segment-contacts', { list_id: 'list-1', threshold: 0.78 });
    expect(result.current.data?.segmented).toBe(12);
    expect(result.current.data?.persisted).toHaveLength(2);
  });
});
