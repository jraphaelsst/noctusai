/**
 * Wave 2 (cache-invalidation narrowing) — useClientes.ts, the 'funil' key.
 *
 * Since the P1.5.4 reshape (useFunil.ts's own docblock) the funil board's
 * cards are `negociacoes_venda` rows, not clientes:
 *  - useCreateCliente: dropped 'funil' — a new cliente has no negociação
 *    yet (criar_cliente only INSERTs into `clientes`).
 *  - useToggleArquivarCliente: dropped 'funil' — the board filters on the
 *    NEGOCIAÇÃO's own `arquivado` column, not the cliente's, and the
 *    nested cliente join doesn't project `arquivado` either.
 *  - useUpdateCliente: KEPT 'funil' — the board's nested cliente join
 *    projects nome/email/telefone/origem, all editable here.
 *  - useDeleteCliente: KEPT 'funil' — `negociacoes_venda.cliente_id` is
 *    `ON DELETE CASCADE`, so deleting a cliente deletes its open deals too.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockPost = vi.fn();
const mockPatch = vi.fn();
const mockDelete = vi.fn();
const mockAuth = { user: { id: 'u1', email: 'u@test' } };

vi.mock('@noctusai/seed/infra', () => ({
  api: { get: vi.fn(), post: mockPost, patch: mockPatch, delete: mockDelete },
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

describe('useClientes — funil invalidation only where a deal can actually change', () => {
  beforeEach(() => vi.clearAllMocks());

  it('useCreateCliente does NOT invalidate funil', async () => {
    mockPost.mockResolvedValue({ data: { id: 'cl1' } });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useCreateCliente } = await import('@/hooks/useClientes');
    const { result } = renderHook(() => useCreateCliente(), { wrapper });

    result.current.mutate({ nome: 'Fulano' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['clientes'] });
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: ['funil'] });
  });

  it('useToggleArquivarCliente does NOT invalidate funil', async () => {
    mockPost.mockResolvedValue({ data: { id: 'cl1', arquivado: true } });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useToggleArquivarCliente } = await import('@/hooks/useClientes');
    const { result } = renderHook(() => useToggleArquivarCliente(), { wrapper });

    result.current.mutate('cl1');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['clientes'] });
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: ['funil'] });
  });

  it('useUpdateCliente KEEPS the funil invalidation (nested join fields)', async () => {
    mockPatch.mockResolvedValue({ data: { id: 'cl1', nome: 'Novo Nome' } });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useUpdateCliente } = await import('@/hooks/useClientes');
    const { result } = renderHook(() => useUpdateCliente(), { wrapper });

    result.current.mutate({ id: 'cl1', nome: 'Novo Nome' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['funil'] });
  });

  it('useDeleteCliente KEEPS the funil invalidation (cascade delete)', async () => {
    mockDelete.mockResolvedValue({});
    const { wrapper, invalidateSpy } = makeWrapper();
    const { useDeleteCliente } = await import('@/hooks/useClientes');
    const { result } = renderHook(() => useDeleteCliente(), { wrapper });

    result.current.mutate('cl1');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['funil'] });
  });
});
