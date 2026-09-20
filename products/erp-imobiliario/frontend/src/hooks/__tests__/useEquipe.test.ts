/**
 * useEquipe hook tests — 2026-09-20 wiring audit, task 6.
 *
 * `useRemoveMember` used to call `DELETE /api/team/members/{id}`, but the
 * framework only ships `DELETE /api/team/{user_id}`
 * (`seed/framework/backend/noctusai_seed/routers.py`) — no `/members/`
 * segment. Every removal 404'd. Pins the corrected URL.
 *
 * Pattern mirrors `useToggleCompartilhamento.test.ts`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockDelete = vi.fn();

vi.mock('@noctusai/seed/infra', () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: mockDelete },
  useAuthStore: () => ({ user: { id: 'u1', email: 'u@test' } }),
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

describe('useRemoveMember', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('DELETEs /api/team/{id} — no /members/ segment', async () => {
    mockDelete.mockResolvedValue({ ok: true });
    const { wrapper } = makeWrapper();
    const { useRemoveMember } = await import('@/hooks/useEquipe');
    const { result } = renderHook(() => useRemoveMember(), { wrapper });

    result.current.mutate('user-42');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockDelete).toHaveBeenCalledWith('/api/team/user-42');
  });

  it('invalidates the team-members query on success', async () => {
    mockDelete.mockResolvedValue({ ok: true });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useRemoveMember } = await import('@/hooks/useEquipe');
    const { result } = renderHook(() => useRemoveMember(), { wrapper });

    result.current.mutate('user-42');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['team-members'] });
  });
});
