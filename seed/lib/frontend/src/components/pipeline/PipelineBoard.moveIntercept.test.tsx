/**
 * Tests for `PipelineBoard`'s opt-in move intercept (`onBeforeMove`,
 * `onMoveError`) — the SNAP-BACK-UNTIL-CONFIRMED contract documented in
 * `PipelineBoard.tsx`'s module header.
 *
 * `KanbanBoard` is mocked: `@dnd-kit`'s sensors need real layout geometry
 * jsdom does not compute (`reference_lib_frontend_vitest_render_harness_gap`
 * in memory — same reason `KanbanBoard.test.tsx` drives `computeMove`
 * directly instead of simulating a drag). The mock exposes ONE button that
 * calls the `onMove` prop PipelineBoard wires up, with the exact signature a
 * real drop ends in: `(cardId, fromStage, toStage, toIndex)`. That is enough
 * to drive `handleMove`'s actual logic — the thing this file tests — without
 * re-testing `KanbanBoard`'s own drag mechanics.
 */
/// <reference types="@testing-library/jest-dom" />
import * as React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

import { PipelineBoard } from './PipelineBoard';
import { createPipelineHooks } from './createPipelineHooks';
import type { PipelineApi, PipelineColumn, PipelineStage } from './types';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

vi.mock('../kanban', () => ({
  KanbanBoard: (props: any) => (
    <div>
      {props.columns
        .flatMap((c: any) => c.cards)
        .map((card: any) => (
          <React.Fragment key={props.getCardId(card)}>
            {props.renderCard(card, { isDragging: false })}
          </React.Fragment>
        ))}
      <button onClick={() => props.onMove('c1', STAGE_A, STAGE_B, 0)}>trigger-move</button>
    </div>
  ),
}));

interface Card {
  id: string;
  valor: number;
}

const STAGE_A = 'stage-a';
const STAGE_B = 'stage-b';

function stage(id: string, posicao: number): PipelineStage {
  return { id, slug: id, label: id.toUpperCase(), cor: 'secondary', posicao, papel: null, ativo: true };
}

function board(): PipelineColumn<Card>[] {
  return [
    { etapa: STAGE_A, stage: stage(STAGE_A, 0), total: 1, valorTotal: 100, cards: [{ id: 'c1', valor: 100 }] },
    { etapa: STAGE_B, stage: stage(STAGE_B, 1), total: 0, valorTotal: 0, cards: [] },
  ];
}

let api: PipelineApi;
let queryClient: QueryClient;

function makeHooks() {
  return createPipelineHooks<Card>(
    {
      queryKey: 'ibboard',
      boardEndpoint: '/api/board',
      moveEndpoint: '/api/cards',
      getCardId: (c) => c.id,
      getCardValue: (c) => c.valor,
      entityLabel: 'carta',
    },
    api,
  );
}

beforeEach(() => {
  queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  api = {
    get: vi.fn(async () => ({ data: board() })) as unknown as PipelineApi['get'],
    post: vi.fn() as unknown as PipelineApi['post'],
    patch: vi.fn() as unknown as PipelineApi['patch'],
    delete: vi.fn() as unknown as PipelineApi['delete'],
  };
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderBoard(props: Record<string, unknown> = {}) {
  const hooks = makeHooks();
  render(
    <QueryClientProvider client={queryClient}>
      <PipelineBoard hooks={hooks} renderCard={(c: Card) => <span>{c.id}</span>} {...props} />
    </QueryClientProvider>,
  );
  return hooks;
}

describe('PipelineBoard — onBeforeMove is opt-in', () => {
  it('DEFAULT (no onBeforeMove): a drop mutates immediately, unchanged from before', async () => {
    (api.post as any).mockResolvedValue({ data: { id: 'c1', valor: 100 } });
    renderBoard();
    await screen.findByText('c1');

    fireEvent.click(screen.getByText('trigger-move'));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/api/cards/c1/mover-etapa', {
        para_etapa_id: STAGE_B,
        novo_indice: 0,
        motivo: undefined,
      }),
    );
  });
});

describe('PipelineBoard — onBeforeMove: cancel', () => {
  it('`false` cancels: the intercept receives a full ctx and the mutation never fires', async () => {
    const onBeforeMove = vi.fn().mockResolvedValue(false);
    renderBoard({ onBeforeMove });
    await screen.findByText('c1');

    fireEvent.click(screen.getByText('trigger-move'));

    await waitFor(() =>
      expect(onBeforeMove).toHaveBeenCalledWith(
        expect.objectContaining({
          toIndex: 0,
          direction: 'forward',
          stepDistance: 1,
          fromStage: expect.objectContaining({ id: STAGE_A }),
          toStage: expect.objectContaining({ id: STAGE_B }),
          card: expect.objectContaining({ id: 'c1' }),
        }),
      ),
    );

    // Let any (incorrect) mutate call have a tick to fire before asserting its absence.
    await act(async () => {
      await Promise.resolve();
    });
    expect(api.post).not.toHaveBeenCalled();
  });
});

describe('PipelineBoard — onBeforeMove: motivo/extra merge', () => {
  it('an object decision merges `motivo` + `extra` into the mover-etapa POST body', async () => {
    (api.post as any).mockResolvedValue({ data: { id: 'c1', valor: 100 } });
    const onBeforeMove = vi.fn().mockResolvedValue({ motivo: 'aprovado', extra: { aprovado_por: 'u-1' } });
    renderBoard({ onBeforeMove });
    await screen.findByText('c1');

    fireEvent.click(screen.getByText('trigger-move'));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/api/cards/c1/mover-etapa', {
        para_etapa_id: STAGE_B,
        novo_indice: 0,
        motivo: 'aprovado',
        aprovado_por: 'u-1',
      }),
    );
  });

  it('`true` proceeds with no motivo/extra', async () => {
    (api.post as any).mockResolvedValue({ data: { id: 'c1', valor: 100 } });
    const onBeforeMove = vi.fn().mockResolvedValue(true);
    renderBoard({ onBeforeMove });
    await screen.findByText('c1');

    fireEvent.click(screen.getByText('trigger-move'));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/api/cards/c1/mover-etapa', {
        para_etapa_id: STAGE_B,
        novo_indice: 0,
        motivo: undefined,
      }),
    );
  });
});

describe('PipelineBoard — snap-back-until-confirmed', () => {
  it('dims the card while the decision is pending and never mutates until it resolves', async () => {
    let resolveDecision!: (d: unknown) => void;
    const onBeforeMove = vi.fn(() => new Promise((resolve) => { resolveDecision = resolve; }));
    (api.post as any).mockResolvedValue({ data: { id: 'c1', valor: 100 } });
    renderBoard({ onBeforeMove });
    await screen.findByText('c1');

    fireEvent.click(screen.getByText('trigger-move'));
    await waitFor(() => expect(onBeforeMove).toHaveBeenCalled());

    expect(screen.getByText('c1').closest('[aria-busy="true"]')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();

    await act(async () => {
      resolveDecision(true);
    });

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    expect(screen.getByText('c1').closest('[aria-busy="true"]')).toBeNull();
  });
});

describe('PipelineBoard — onMoveError', () => {
  it('a move the SERVER rejects rolls back the optimistic update and fires onMoveError instead of the default toast', async () => {
    const filtros = {};
    queryClient.setQueryData(['ibboard', filtros], board());
    let fail!: (e: Error) => void;
    (api.post as any).mockImplementation(
      () => new Promise((_resolve, reject) => { fail = reject; }),
    );
    const onMoveError = vi.fn();
    const { toast } = await import('sonner');

    renderBoard({ onMoveError });
    await screen.findByText('c1');

    fireEvent.click(screen.getByText('trigger-move'));

    // 1. the optimistic move DID land first — otherwise the rollback assertion below is a false green.
    await waitFor(() => {
      const data = queryClient.getQueryData<PipelineColumn<Card>[]>(['ibboard', filtros])!;
      expect(data[1].cards.map((c) => c.id)).toEqual(['c1']);
    });

    await act(async () => {
      fail(new Error('etapa bloqueada'));
    });

    await waitFor(() =>
      expect(onMoveError).toHaveBeenCalledWith(
        expect.objectContaining({ message: 'etapa bloqueada' }),
        expect.objectContaining({ cardId: 'c1', toStageId: STAGE_B }),
      ),
    );
    expect(toast.error).not.toHaveBeenCalled();

    // 2. ...and is fully undone.
    const data = queryClient.getQueryData<PipelineColumn<Card>[]>(['ibboard', filtros])!;
    expect(data[0].cards.map((c) => c.id)).toEqual(['c1']);
    expect(data[1].cards).toEqual([]);
  });

  it('`onBeforeMove` itself throwing surfaces via onMoveError — nothing was mutated, so nothing rolls back', async () => {
    const onBeforeMove = vi.fn().mockRejectedValue(new Error('regra falhou'));
    const onMoveError = vi.fn();
    renderBoard({ onBeforeMove, onMoveError });
    await screen.findByText('c1');

    fireEvent.click(screen.getByText('trigger-move'));

    await waitFor(() =>
      expect(onMoveError).toHaveBeenCalledWith(
        expect.objectContaining({ message: 'regra falhou' }),
        expect.objectContaining({ cardId: 'c1', toStageId: STAGE_B }),
      ),
    );
    expect(api.post).not.toHaveBeenCalled();
  });
});
