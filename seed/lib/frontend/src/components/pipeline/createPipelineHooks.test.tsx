/**
 * Tests for `createPipelineHooks` — the data half of the kanban organ.
 *
 * The optimistic-move mutation is the reason this factory exists: it was
 * written three times (ERP Funil, ERP Processos, orbity Funil) and each copy
 * independently rediscovered the same traps. These tests pin the traps:
 *
 *  - snapshot/restore via `getQueriesData`, NOT `getQueryData` — the cache key
 *    carries the active filters, so a bare read snapshots an empty entry and
 *    the rollback silently restores nothing.
 *  - totals recomputed on BOTH columns — the card left one and joined another.
 *  - a rename invalidates the BOARD too, not just the stage list, because the
 *    column headers ship with the board payload.
 *
 * Drag itself is not simulated: `@dnd-kit` sensors need real layout geometry
 * that jsdom does not compute (see `reference_lib_frontend_vitest_render_harness_gap`).
 * These tests drive the mutation directly, which is where the logic lives.
 */
import * as React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor, act, cleanup } from '@testing-library/react';

import { createPipelineHooks } from './createPipelineHooks';
import type { PipelineApi, PipelineColumn } from './types';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

interface Card {
  id: string;
  valor: number;
}

const STAGE_A = 'stage-a';
const STAGE_B = 'stage-b';

function board(): PipelineColumn<Card>[] {
  return [
    {
      etapa: STAGE_A,
      stage: { id: STAGE_A, slug: 'a', label: 'A', cor: 'secondary', posicao: 0, papel: null, ativo: true },
      total: 2,
      valorTotal: 300,
      cards: [{ id: 'c1', valor: 100 }, { id: 'c2', valor: 200 }],
    },
    {
      etapa: STAGE_B,
      stage: { id: STAGE_B, slug: 'b', label: 'B', cor: 'primary', posicao: 1, papel: null, ativo: true },
      total: 0,
      valorTotal: 0,
      cards: [],
    },
  ];
}

let api: PipelineApi;
let queryClient: QueryClient;

function makeHooks() {
  return createPipelineHooks<Card>(
    {
      queryKey: 'testboard',
      boardEndpoint: '/api/board',
      stagesEndpoint: '/api/board/etapas',
      moveEndpoint: '/api/cards',
      getCardId: (c) => c.id,
      getCardValue: (c) => c.valor,
      entityLabel: 'carta',
    },
    api,
  );
}

function wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  api = {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  };
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('useBoard', () => {
  it('unwraps the { data } envelope and forwards filters', async () => {
    (api.get as any).mockResolvedValue({ data: board() });
    const hooks = makeHooks();

    const { result } = renderHook(() => hooks.useBoard({ busca: 'joão' }), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.get).toHaveBeenCalledWith('/api/board', { busca: 'joão' });
    expect(result.current.data?.[0].etapa).toBe(STAGE_A);
  });

  it('never resolves to undefined — an undefined queryFn result never populates the cache', async () => {
    (api.get as any).mockResolvedValue(undefined);
    const hooks = makeHooks();

    const { result } = renderHook(() => hooks.useBoard(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([]);
  });
});

describe('useMoveCard — optimistic update', () => {
  it('moves the card and recomputes totals on BOTH columns', async () => {
    const filtros = { busca: 'x' };
    queryClient.setQueryData(['testboard', filtros], board());
    // Never resolves, so the optimistic state is observable.
    (api.post as any).mockImplementation(() => new Promise(() => {}));

    const hooks = makeHooks();
    const { result } = renderHook(() => hooks.useMoveCard(), { wrapper });

    act(() => {
      result.current.mutate({ cardId: 'c1', toStageId: STAGE_B, toIndex: 0 });
    });

    await waitFor(() => {
      const data = queryClient.getQueryData<PipelineColumn<Card>[]>(['testboard', filtros]);
      expect(data?.[1].cards.map((c) => c.id)).toEqual(['c1']);
    });

    const data = queryClient.getQueryData<PipelineColumn<Card>[]>(['testboard', filtros])!;
    // Source column shrank...
    expect(data[0].total).toBe(1);
    expect(data[0].valorTotal).toBe(200);
    // ...and the destination grew. A version that only recomputed the target
    // leaves the source showing a stale count.
    expect(data[1].total).toBe(1);
    expect(data[1].valorTotal).toBe(100);
  });

  it('rolls back a FILTERED cache entry on error', async () => {
    // The regression guard for getQueryData-vs-getQueriesData: the entry lives
    // under ['testboard', {...filtros}], never the bare key.
    const filtros = { busca: 'x' };
    queryClient.setQueryData(['testboard', filtros], board());

    // Reject only when we say so, so the optimistic state is observable first.
    // Without this the test is a FALSE GREEN: if the optimistic update never
    // applied to the filtered key, the cache would be untouched at the end and
    // every assertion below would still pass.
    let fail!: (e: Error) => void;
    (api.post as any).mockImplementation(
      () => new Promise((_resolve, reject) => { fail = reject; }),
    );

    const hooks = makeHooks();
    const { result } = renderHook(() => hooks.useMoveCard(), { wrapper });

    act(() => {
      result.current.mutate({ cardId: 'c1', toStageId: STAGE_B, toIndex: 0 });
    });

    // 1. the optimistic move DID land on the filtered entry
    await waitFor(() => {
      const mid = queryClient.getQueryData<PipelineColumn<Card>[]>(['testboard', filtros])!;
      expect(mid[1].cards.map((c) => c.id)).toEqual(['c1']);
    });

    // 2. ...and is fully undone on failure
    await act(async () => {
      fail(new Error('boom'));
    });
    await waitFor(() => expect(result.current.isError).toBe(true));

    const data = queryClient.getQueryData<PipelineColumn<Card>[]>(['testboard', filtros])!;
    expect(data[0].cards.map((c) => c.id)).toEqual(['c1', 'c2']);
    expect(data[0].total).toBe(2);
    expect(data[1].cards).toEqual([]);
  });

  it('posts the stage ID, not a stage name', async () => {
    (api.post as any).mockResolvedValue({ data: { id: 'c1', valor: 100 } });
    const hooks = makeHooks();
    const { result } = renderHook(() => hooks.useMoveCard(), { wrapper });

    act(() => {
      result.current.mutate({ cardId: 'c1', toStageId: STAGE_B, toIndex: 2, motivo: 'porque sim' });
    });

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    expect(api.post).toHaveBeenCalledWith('/api/cards/c1/mover-etapa', {
      para_etapa_id: STAGE_B,
      novo_indice: 2,
      motivo: 'porque sim',
    });
  });

  it('is a no-op on the cache when the card is not present', async () => {
    queryClient.setQueryData(['testboard', {}], board());
    (api.post as any).mockImplementation(() => new Promise(() => {}));
    const hooks = makeHooks();
    const { result } = renderHook(() => hooks.useMoveCard(), { wrapper });

    act(() => {
      result.current.mutate({ cardId: 'ghost', toStageId: STAGE_B });
    });

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const data = queryClient.getQueryData<PipelineColumn<Card>[]>(['testboard', {}])!;
    expect(data[0].cards).toHaveLength(2);
  });
});

describe('stage CRUD', () => {
  it('a rename invalidates the BOARD as well as the stage list', async () => {
    // Column headers ship with the board payload, so refreshing only the stage
    // list leaves the old label on screen — which reads as "rename didn't work".
    const spy = vi.spyOn(queryClient, 'invalidateQueries');
    (api.patch as any).mockResolvedValue({ data: { id: 's1', label: 'Novo' } });

    const hooks = makeHooks();
    const { result } = renderHook(() => hooks.useUpdateStage(), { wrapper });

    act(() => {
      result.current.mutate({ id: 's1', input: { label: 'Novo' } });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const keys = spy.mock.calls.map((c) => JSON.stringify((c[0] as any).queryKey));
    expect(keys).toContain(JSON.stringify(['testboard-stages']));
    expect(keys).toContain(JSON.stringify(['testboard']));
  });

  it('passes reassign_to as a query param when deleting a non-empty stage', async () => {
    (api.delete as any).mockResolvedValue({ data: { cards_movidos: 3 } });
    const hooks = makeHooks();
    const { result } = renderHook(() => hooks.useDeleteStage(), { wrapper });

    act(() => {
      result.current.mutate({ id: 's1', reassignTo: 's2' });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.delete).toHaveBeenCalledWith('/api/board/etapas/s1', { reassign_to: 's2' });
  });

  it('omits reassign_to entirely when none is given', async () => {
    (api.delete as any).mockResolvedValue({ data: { cards_movidos: 0 } });
    const hooks = makeHooks();
    const { result } = renderHook(() => hooks.useDeleteStage(), { wrapper });

    act(() => {
      result.current.mutate({ id: 's1' });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.delete).toHaveBeenCalledWith('/api/board/etapas/s1', undefined);
  });

  it('reorder posts the full ordered id list', async () => {
    (api.post as any).mockResolvedValue({ data: [] });
    const hooks = makeHooks();
    const { result } = renderHook(() => hooks.useReorderStages(), { wrapper });

    act(() => {
      result.current.mutate(['s3', 's1', 's2']);
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.post).toHaveBeenCalledWith('/api/board/etapas/reordenar', {
      ordem: ['s3', 's1', 's2'],
    });
  });
});
