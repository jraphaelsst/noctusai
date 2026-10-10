/**
 * `PipelineBoard` `showValue` — the per-column value line is on by default
 * (every money board unchanged) and `showValue={false}` removes it, so a board
 * with no money does not leave an empty `<p>` under every header.
 */
/// <reference types="@testing-library/jest-dom" />
import * as React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen } from '@testing-library/react';

import { PipelineBoard } from './PipelineBoard';
import { createPipelineHooks } from './createPipelineHooks';
import type { PipelineApi, PipelineColumn, PipelineStage } from './types';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

interface Card {
  id: string;
  valor: number;
}

const STAGE: PipelineStage = {
  id: 'a',
  slug: 'a',
  label: 'A',
  cor: 'secondary',
  posicao: 0,
  papel: null,
  ativo: true,
};

const COLUMNS: PipelineColumn<Card>[] = [
  { etapa: 'a', stage: STAGE, total: 1, valorTotal: 4242, cards: [{ id: 'k1', valor: 4242 }] },
];

function renderBoard(props: Record<string, unknown> = {}) {
  const api = {
    get: vi.fn(async () => ({ data: COLUMNS })) as unknown as PipelineApi['get'],
    post: vi.fn(async () => ({ data: null })) as unknown as PipelineApi['post'],
    patch: vi.fn(async () => ({ data: null })) as unknown as PipelineApi['patch'],
    delete: vi.fn(async () => ({ data: null })) as unknown as PipelineApi['delete'],
  } as PipelineApi;
  const hooks = createPipelineHooks<Card>(
    {
      queryKey: 'showvalue',
      boardEndpoint: '/api/board',
      stagesEndpoint: '/api/board/etapas',
      moveEndpoint: '/api/cards',
      getCardId: (c) => c.id,
      getCardValue: (c) => c.valor,
      entityLabel: 'carta',
    },
    api,
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <PipelineBoard
        hooks={hooks}
        renderCard={(c: Card) => <span>{c.id}</span>}
        formatValue={(v: number) => `R$ ${v}`}
        {...props}
      />
    </QueryClientProvider>,
  );
}

afterEach(cleanup);

describe('PipelineBoard showValue', () => {
  it('DEFAULT renders the column value line', async () => {
    renderBoard();
    await screen.findByText('k1');
    expect(screen.getByText('R$ 4242')).toBeInTheDocument();
  });

  it('showValue={false} renders no value line', async () => {
    renderBoard({ showValue: false });
    await screen.findByText('k1');
    expect(screen.queryByText('R$ 4242')).toBeNull();
  });
});
