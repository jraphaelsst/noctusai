/**
 * Tests for the Edição de Fotos hook factory — focused on the binding
 * loading-state contract (CLAUDE.md §1 / contract §9): every read hook must
 * expose `showSkeleton`/`isRefreshing` already correctly computed, and
 * `useRevisao` must carry `placeholderData` so a `loteId` key change never
 * drops to an empty list mid-fetch.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook, waitFor, act, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { createEdicaoFotosHooks, type Capacidades, type FotoRevisao } from './hooks';
import type { ApiClient } from '../api';

afterEach(cleanup);

function makeApi(overrides: Partial<ApiClient> = {}): ApiClient {
  return {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    upload: vi.fn(),
    ...overrides,
  } as unknown as ApiClient;
}

function wrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  }
  return Wrapper;
}

const CAPACIDADES: Capacidades = {
  pode_criar_lote: true,
  pode_ver_veredito: false,
  pode_gerir_pool: false,
  pode_aprovar_regras: false,
  pode_ativar_guia: false,
  dashboard: null,
  modelo_configurado: true,
  economico_disponivel: false,
  economico_bloqueado_motivo: 'modelo_sem_batch',
  tipos_edicao_ativos: ['cor_luz'],
  limites: { fotos_por_lote: 100, bytes_por_foto: 26214400 },
};

// ── useCapacidades — showSkeleton / not lying ────────────────────────────────

describe('useCapacidades: loading contract', () => {
  it('showSkeleton is true while pending with no data, false once resolved', async () => {
    const api = makeApi({ get: vi.fn().mockResolvedValue(CAPACIDADES) });
    const { useCapacidades } = createEdicaoFotosHooks(api);
    const { result } = renderHook(() => useCapacidades(), { wrapper: wrapper() });

    expect(result.current.showSkeleton).toBe(true);
    expect(result.current.isRefreshing).toBe(false);

    await waitFor(() => expect(result.current.capacidades).toEqual(CAPACIDADES));
    expect(result.current.showSkeleton).toBe(false);
  });

  it('isRefreshing is true (not showSkeleton) during a background refetch that keeps existing data', async () => {
    let resolveSecond: (v: Capacidades) => void;
    const secondCall = new Promise<Capacidades>((resolve) => {
      resolveSecond = resolve;
    });
    const get = vi
      .fn()
      .mockResolvedValueOnce(CAPACIDADES)
      .mockReturnValueOnce(secondCall);
    const api = makeApi({ get });
    const { useCapacidades } = createEdicaoFotosHooks(api);
    const { result } = renderHook(() => useCapacidades(), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.capacidades).toEqual(CAPACIDADES));

    act(() => {
      void result.current.refetch();
    });

    await waitFor(() => expect(result.current.isRefreshing).toBe(true));
    // Never a lying skeleton — data is still there, this is a refresh, not a load.
    expect(result.current.showSkeleton).toBe(false);
    expect(result.current.capacidades).toEqual(CAPACIDADES);

    resolveSecond!({ ...CAPACIDADES, pode_criar_lote: false });
    await waitFor(() => expect(result.current.isRefreshing).toBe(false));
    expect(result.current.capacidades?.pode_criar_lote).toBe(false);
  });
});

// ── useRevisao — placeholderData across a loteId key change ─────────────────

describe('useRevisao: batch-key change never drops to empty', () => {
  const FOTOS_LOTE_A: FotoRevisao[] = [
    {
      id: 'f1',
      url_antes: 'a.jpg',
      url_depois: 'a-edit.jpg',
      estado: 'aguardando_decisao',
      decisao: null,
      comentario: null,
    },
  ];

  it('keeps the previous batch photos as placeholder data while the next batch loads', async () => {
    let resolveLoteB: (v: FotoRevisao[]) => void;
    const loteBPromise = new Promise<FotoRevisao[]>((resolve) => {
      resolveLoteB = resolve;
    });
    const get = vi.fn((path: string): Promise<any> => {
      if (path === '/api/edicao-fotos/revisao/lote-a') return Promise.resolve(FOTOS_LOTE_A);
      if (path === '/api/edicao-fotos/revisao/lote-b') return loteBPromise;
      throw new Error(`unexpected path ${path}`);
    });
    const api = makeApi({ get });
    const { useRevisao } = createEdicaoFotosHooks(api);

    const Wrapper = wrapper();
    const { result, rerender } = renderHook(({ loteId }) => useRevisao(loteId), {
      wrapper: Wrapper,
      initialProps: { loteId: 'lote-a' as string },
    });

    await waitFor(() => expect(result.current.fotos).toEqual(FOTOS_LOTE_A));

    rerender({ loteId: 'lote-b' });

    // placeholderData keeps lote A's photos visible — never an empty flash.
    expect(result.current.fotos).toEqual(FOTOS_LOTE_A);
    expect(result.current.isRefreshing).toBe(true);
    expect(result.current.showSkeleton).toBe(false);

    resolveLoteB!([]);
    await waitFor(() => expect(result.current.fotos).toEqual([]));
  });

  it('does not fire the query when loteId is falsy', () => {
    const get = vi.fn();
    const api = makeApi({ get });
    const { useRevisao } = createEdicaoFotosHooks(api);
    renderHook(() => useRevisao(undefined), { wrapper: wrapper() });
    expect(get).not.toHaveBeenCalled();
  });
});
