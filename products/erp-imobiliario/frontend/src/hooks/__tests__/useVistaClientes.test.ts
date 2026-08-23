/**
 * Vista clientes hook tests — the LGPD-relevant behaviour, pinned.
 *
 * These are not generic smoke tests. Each one guards a decision that the
 * Clientes tab's data-minimisation posture depends on, and that a well-meaning
 * later edit could undo without noticing:
 *
 *   - the detail query must not fire without a chosen `codigo`;
 *   - the list query must be gated by the tab, not fire on page load;
 *   - personal data must not be cached long in the browser.
 *
 * Pattern mirrors hooks/__tests__/useCorretorHooks.test.ts.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockGet = vi.fn();

vi.mock('@noctusai/seed/infra', () => ({
  api: { get: mockGet, post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  useAuthStore: () => ({ user: { id: 'u1', email: 'u@test' } }),
}));

function withQueryClient() {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
}

const LIST_ENVELOPE = {
  source: 'vista',
  tab: 'clientes',
  live: true,
  fetched_at: '2026-08-22T12:00:00+00:00',
  pagination: { pagina: 1, quantidade: 2, total: 42960, paginas: 860 },
  items: [
    { codigo: 'C0001', nome: 'Fulana de Tal', celular: '(11) 90000-0000', status: 'Ativo' },
    { codigo: 'C0002', nome: 'Beltrano' },
  ],
  raw_available: false,
  warnings: [],
};

describe('useVistaClientes', () => {
  beforeEach(() => vi.clearAllMocks());

  it('fetches one page and surfaces the envelope', async () => {
    mockGet.mockResolvedValue(LIST_ENVELOPE);
    const { useVistaClientes } = await import('@/hooks/useVistaShowcase');
    const { result } = renderHook(() => useVistaClientes(true, 1, 50, {}), {
      wrapper: withQueryClient(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith('/api/vista-showcase/clientes?page=1&page_size=50');
    expect(result.current.data?.pagination?.total).toBe(42960);
    expect(result.current.data?.items).toHaveLength(2);
  });

  it('does not fire while the tab is disabled', async () => {
    const { useVistaClientes } = await import('@/hooks/useVistaShowcase');
    renderHook(() => useVistaClientes(false, 1, 50, {}), { wrapper: withQueryClient() });
    await new Promise(r => setTimeout(r, 20));
    expect(mockGet).not.toHaveBeenCalled();
  });

  it('passes only the filters that were actually set', async () => {
    mockGet.mockResolvedValue(LIST_ENVELOPE);
    const { useVistaClientes } = await import('@/hooks/useVistaShowcase');
    const { result } = renderHook(
      () => useVistaClientes(true, 2, 50, { nome: 'Fulana', status: '' }),
      { wrapper: withQueryClient() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const url = mockGet.mock.calls[0][0] as string;
    expect(url).toContain('page=2');
    expect(url).toContain('nome=Fulana');
    expect(url).not.toContain('status=');
  });

  it('keeps personal data out of long-lived browser cache', async () => {
    /** The backend refuses to persist Vista payloads; a generous staleTime or
     *  gcTime here would quietly make the browser the cache it declined to be.
     *  Asserted against the registered query options, not against a constant
     *  in this file — otherwise the test passes no matter what the hook does. */
    mockGet.mockResolvedValue(LIST_ENVELOPE);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client }, children);

    const { useVistaClientes } = await import('@/hooks/useVistaShowcase');
    const { result } = renderHook(() => useVistaClientes(true, 1, 50, {}), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const entry = client.getQueryCache().find({
      queryKey: ['vista-showcase', 'clientes', 1, 50, {}],
    });
    expect(entry).toBeDefined();
    const { staleTime, gcTime } = entry!.options as { staleTime?: number; gcTime?: number };
    expect(staleTime).toBeLessThanOrEqual(30_000);
    expect(gcTime).toBeLessThanOrEqual(120_000);
  });
});

describe('useVistaClienteDetalhes', () => {
  beforeEach(() => vi.clearAllMocks());

  it('does NOT fetch until a client is actually opened', async () => {
    /** The single most important assertion in this file: demographics are
     *  reached only by a deliberate act on one named record. A detail query
     *  that fired on mount would read a profile nobody asked for — and would
     *  write a `projection: "detail"` audit row for it. */
    const { useVistaClienteDetalhes } = await import('@/hooks/useVistaShowcase');
    renderHook(() => useVistaClienteDetalhes(null), { wrapper: withQueryClient() });
    await new Promise(r => setTimeout(r, 20));
    expect(mockGet).not.toHaveBeenCalled();
  });

  it('fetches one named client and exposes the demographic block', async () => {
    mockGet.mockResolvedValue({
      ...LIST_ENVELOPE,
      tab: 'clientes-detalhes',
      items: [{
        codigo: 'C0001',
        base: { codigo: 'C0001', nome: 'Fulana de Tal', celular: '(11) 90000-0000' },
        data_nascimento: '1990-04-02',
        sexo: 'F',
        estado_civil: 'Solteira',
        profissao: 'Arquiteta',
      }],
    });
    const { useVistaClienteDetalhes } = await import('@/hooks/useVistaShowcase');
    const { result } = renderHook(() => useVistaClienteDetalhes('C0001'), {
      wrapper: withQueryClient(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith('/api/vista-showcase/clientes/C0001');
    expect(result.current.data?.data_nascimento).toBe('1990-04-02');
    expect(result.current.data?.base.nome).toBe('Fulana de Tal');
  });

  it('url-encodes the codigo instead of interpolating it raw', async () => {
    mockGet.mockResolvedValue({ ...LIST_ENVELOPE, items: [] });
    const { useVistaClienteDetalhes } = await import('@/hooks/useVistaShowcase');
    const { result } = renderHook(() => useVistaClienteDetalhes('C/01 ?x'), {
      wrapper: withQueryClient(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith('/api/vista-showcase/clientes/C%2F01%20%3Fx');
  });
});
