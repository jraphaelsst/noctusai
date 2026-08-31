/**
 * Wave-2 fix-on-contact test — useAgenda.ts mutations now also invalidate
 * "dashboard-today-events" (useDashboard.ts's `useDashboardTodayEvents`),
 * which hits the exact same `/api/schedule` endpoint as "agenda" under a
 * different query key.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockPost = vi.fn();

vi.mock('@noctusai/seed/infra', () => ({
  api: { get: vi.fn(), post: mockPost, patch: vi.fn(), delete: vi.fn() },
  useAuthStore: () => ({ user: { id: 'u1' } }),
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

describe('useAgenda invalidation (wave-2 fix-on-contact)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('useCreateEvento invalidates agenda AND dashboard-today-events', async () => {
    mockPost.mockResolvedValue({ data: { id: 'e1' } });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useCreateEvento } = await import('@/hooks/useAgenda');
    const { result } = renderHook(() => useCreateEvento(), { wrapper });

    result.current.mutate({ titulo: 'Reuniao' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const keys = invalidateSpy.mock.calls.map((c) => (c[0] as { queryKey: unknown[] }).queryKey);
    expect(keys).toContainEqual(['agenda']);
    expect(keys).toContainEqual(['dashboard-today-events']);
  });
});
