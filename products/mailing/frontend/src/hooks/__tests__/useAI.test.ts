/**
 * useAI hook tests — Mailing AI features.
 *
 * Mirrors the canonical pattern from products/erp-imobiliario/frontend/src/hooks/__tests__/useAI.test.ts:
 * `renderHook` from @testing-library/react with a QueryClientProvider wrapper;
 * each test stubs `api.post` and asserts the mutation hits the correct URL with
 * the correct payload + parses the response shape. No real network.
 *
 * Phase 2 (2026-05-11, mailing-wiring) orphan-hook triage: dropped the 5
 * Phase-14 test-only hooks (subjects/template-draft/reengagement/deliverability/
 * translate) — their backend routes remain (planned UI work, Q2 in PROJECT.md).
 * Kept the M3 segmentation hook test (wired by Contacts.tsx).
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
