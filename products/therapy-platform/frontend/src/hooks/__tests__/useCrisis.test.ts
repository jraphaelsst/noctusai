/**
 * useCrisis hook tests — 2026-09-20 wiring audit, task 5.
 *
 * `useReviewCrisisAlert` used to call `api.post`, while the backend route
 * is `@router.patch("/{alert_id}/review")` — every review request 405'd,
 * the optimistic update rolled back, and a clinician could believe a
 * suicide-risk alert was reviewed when it never was. Pins `api.patch`
 * being the ONLY method the mutation ever calls.
 *
 * Pattern mirrors `useConsents.test.ts`: stub `api.*` at
 * `@noctusai/seed/infra`, silence `sonner` toasts, render hooks inside a
 * fresh QueryClient provider per test.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();

vi.mock('@noctusai/seed/infra', () => ({
  api: { get: mockGet, post: mockPost, patch: mockPatch },
  useAuthStore: () => ({ user: { id: 'user-test', user_metadata: {} } }),
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

describe('useCrisis hooks', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('useReviewCrisisAlert PATCHes /api/crisis-alerts/:id/review, never POSTs', async () => {
    mockPatch.mockResolvedValue({ data: { id: 'a1', status: 'revisado' } });

    const { useReviewCrisisAlert } = await import('@/hooks/useCrisis');
    const { result } = renderHook(() => useReviewCrisisAlert(), { wrapper: withQueryClient() });

    result.current.mutate({ id: 'a1', status: 'revisado' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockPatch).toHaveBeenCalledWith('/api/crisis-alerts/a1/review', { status: 'revisado' });
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('useCrisisAlerts GETs the paginated list and unwraps the response', async () => {
    mockGet.mockResolvedValue({ data: [{ id: 'a1' }], total: 1 });

    const { useCrisisAlerts } = await import('@/hooks/useCrisis');
    const { result } = renderHook(() => useCrisisAlerts(1, 20), { wrapper: withQueryClient() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockGet).toHaveBeenCalledWith('/api/crisis-alerts?page=1&page_size=20');
    expect(result.current.data?.data).toHaveLength(1);
  });
});
