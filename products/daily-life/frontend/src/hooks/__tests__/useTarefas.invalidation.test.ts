/**
 * Wave-2 fix-on-contact test — useTarefas.ts mutations now also invalidate
 * "dashboard-task-stats" (useDashboard.ts's `useDashboardTaskStats`), which
 * hits the exact same `/api/tasks/stats/resumo` endpoint as "tarefas-stats"
 * under a different query key.
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

describe('useTarefas invalidation (wave-2 fix-on-contact)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('useCreateTarefa invalidates tarefas, tarefas-stats AND dashboard-task-stats', async () => {
    mockPost.mockResolvedValue({ data: { id: 't1' } });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useCreateTarefa } = await import('@/hooks/useTarefas');
    const { result } = renderHook(() => useCreateTarefa(), { wrapper });

    result.current.mutate({ titulo: 'Nova tarefa' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const keys = invalidateSpy.mock.calls.map((c) => (c[0] as { queryKey: unknown[] }).queryKey);
    expect(keys).toContainEqual(['tarefas']);
    expect(keys).toContainEqual(['tarefas-stats']);
    expect(keys).toContainEqual(['dashboard-task-stats']);
  });
});
