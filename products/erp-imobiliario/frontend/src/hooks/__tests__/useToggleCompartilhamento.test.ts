/**
 * useToggleCompartilhamento mutation smoke test — LGPD per-document
 * portal-sharing gate (erp-portal-documentos-sharing-gate, Phase P4).
 *
 * Pattern mirrors hooks/__tests__/useCorretorHooks.test.ts. Verifies the
 * mutation hits PATCH /api/documentos/{id}/compartilhamento with the
 * { shared } body, surfaces the parsed `data` row (never undefined), and
 * invalidates the docs query on success.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockPatch = vi.fn();
const mockAuth = { user: { id: 'u1', email: 'u@test' } };

vi.mock('@noctusai/seed/infra', () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: mockPatch, delete: vi.fn() },
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

describe('useToggleCompartilhamento', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('PATCHes /compartilhamento with { shared: true } and returns the row', async () => {
    mockPatch.mockResolvedValue({
      data: { id: 'd1', nome: 'Contrato.pdf', compartilhado_portal: true },
    });
    const { wrapper } = makeWrapper();
    const { useToggleCompartilhamento } = await import('@/hooks/useDocumentos');
    const { result } = renderHook(() => useToggleCompartilhamento(), { wrapper });

    result.current.mutate({ id: 'd1', shared: true });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPatch).toHaveBeenCalledWith(
      '/api/documentos/d1/compartilhamento',
      { shared: true },
    );
    // queryFn/mutationFn never returns undefined — the typed row is surfaced.
    expect(result.current.data).toEqual({
      id: 'd1',
      nome: 'Contrato.pdf',
      compartilhado_portal: true,
    });
  });

  it('PATCHes with { shared: false } when un-sharing', async () => {
    mockPatch.mockResolvedValue({
      data: { id: 'd2', compartilhado_portal: false },
    });
    const { wrapper } = makeWrapper();
    const { useToggleCompartilhamento } = await import('@/hooks/useDocumentos');
    const { result } = renderHook(() => useToggleCompartilhamento(), { wrapper });

    result.current.mutate({ id: 'd2', shared: false });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPatch).toHaveBeenCalledWith(
      '/api/documentos/d2/compartilhamento',
      { shared: false },
    );
  });

  it('invalidates the documentos query on success', async () => {
    mockPatch.mockResolvedValue({ data: { id: 'd3', compartilhado_portal: true } });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useToggleCompartilhamento } = await import('@/hooks/useDocumentos');
    const { result } = renderHook(() => useToggleCompartilhamento(), { wrapper });

    result.current.mutate({ id: 'd3', shared: true });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['documentos'] });
  });

  it('surfaces the error on mutation failure', async () => {
    mockPatch.mockRejectedValue(new Error('403 Forbidden'));
    const { wrapper } = makeWrapper();
    const { useToggleCompartilhamento } = await import('@/hooks/useDocumentos');
    const { result } = renderHook(() => useToggleCompartilhamento(), { wrapper });

    result.current.mutate({ id: 'd4', shared: true });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe('403 Forbidden');
  });
});
