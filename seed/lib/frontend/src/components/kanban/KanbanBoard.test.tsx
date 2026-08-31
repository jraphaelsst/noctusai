/**
 * Tests for the `KanbanBoard` organ.
 *
 * Two card shapes prove the generality claim (`KB § PATTERNS/architect/
 * seed-canonical-defaults.md` — the organ must not bend either consumer's
 * domain vocabulary):
 *   - erp-shaped: `Cliente { id, nome, etapa_atual }`, columns pre-grouped
 *     server-side (mirrors `products/erp-imobiliario/.../Funil.tsx`).
 *   - orbity-shaped: `Lead { id, name, stage_id }`, columns grouped from
 *     `{ stage: Stage, leads: Lead[] }[]` (mirrors `useCrm.ts`'s `FunilStage`).
 *
 * `computeMove` is tested directly (not via simulated pointer/keyboard drag
 * events) because `@dnd-kit`'s sensors depend on real layout geometry
 * (`getBoundingClientRect`) that jsdom does not compute — see
 * `reference_lib_frontend_vitest_render_harness_gap` in memory. Testing the
 * pure resolution logic proves the actual claim (arbitrary card/stage shapes
 * resolve correctly) without fighting a harness limitation that has nothing
 * to do with this organ's correctness.
 */
/// <reference types="@testing-library/jest-dom" />
import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';

import { KanbanBoard } from './KanbanBoard';
import { computeMove } from './computeMove';
import type { KanbanColumnData } from './types';

afterEach(() => {
  cleanup();
});

// ── erp-shaped fixture ───────────────────────────────────────────────────────

type Etapa = 'novo' | 'contato' | 'proposta';

interface Cliente {
  id: string;
  nome: string;
  etapa_atual: Etapa;
}

function erpColumns(): KanbanColumnData<Cliente, Etapa>[] {
  return [
    {
      stage: { id: 'novo', label: 'Novo' },
      cards: [{ id: 'c1', nome: 'Ana', etapa_atual: 'novo' }],
    },
    {
      stage: { id: 'contato', label: 'Contato' },
      cards: [{ id: 'c2', nome: 'Bruno', etapa_atual: 'contato' }],
    },
    {
      stage: { id: 'proposta', label: 'Proposta' },
      cards: [],
    },
  ];
}

// ── orbity-shaped fixture ────────────────────────────────────────────────────

type StageId = string;

interface Lead {
  id: string;
  name: string;
  stage_id: StageId;
}

function orbityColumns(): KanbanColumnData<Lead, StageId>[] {
  return [
    {
      stage: { id: 'stage-1', label: 'Frio' },
      cards: [{ id: 'l1', name: 'Carla', stage_id: 'stage-1' }],
    },
    {
      stage: { id: 'stage-2', label: 'Quente' },
      cards: [
        { id: 'l2', name: 'Diego', stage_id: 'stage-2' },
        { id: 'l3', name: 'Eva', stage_id: 'stage-2' },
      ],
    },
  ];
}

describe('<KanbanBoard/> — generality across differently-shaped cards', () => {
  it('mounts with erp-shaped data (etapa_atual) and renders every card + column', () => {
    render(
      <KanbanBoard<Cliente, Etapa>
        columns={erpColumns()}
        getCardId={(c) => c.id}
        getCardStage={(c) => c.etapa_atual}
        renderCard={(c) => <span>{c.nome}</span>}
        onMove={() => {}}
      />,
    );

    expect(screen.getByText('Ana')).toBeInTheDocument();
    expect(screen.getByText('Bruno')).toBeInTheDocument();
    expect(screen.getByText('Novo')).toBeInTheDocument();
    expect(screen.getByText('Proposta')).toBeInTheDocument();
    // The empty column's default empty-state renders.
    expect(screen.getByText('Nenhum item nesta etapa')).toBeInTheDocument();
  });

  it('mounts with orbity-shaped data (stage_id, nested stage.name) and renders every card + column', () => {
    render(
      <KanbanBoard<Lead, StageId>
        columns={orbityColumns()}
        getCardId={(l) => l.id}
        getCardStage={(l) => l.stage_id}
        renderCard={(l) => <span>{l.name}</span>}
        onMove={() => {}}
      />,
    );

    expect(screen.getByText('Carla')).toBeInTheDocument();
    expect(screen.getByText('Diego')).toBeInTheDocument();
    expect(screen.getByText('Eva')).toBeInTheDocument();
    expect(screen.getByText('Frio')).toBeInTheDocument();
    expect(screen.getByText('Quente')).toBeInTheDocument();
  });

  it('shows the loading state when there is no data yet (columns empty)', () => {
    render(
      <KanbanBoard<Cliente, Etapa>
        columns={[]}
        getCardId={(c) => c.id}
        getCardStage={(c) => c.etapa_atual}
        renderCard={(c) => <span>{c.nome}</span>}
        onMove={() => {}}
        isLoading
      />,
    );
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('never lets the empty state win over loading when data is still undefined (the 2026-07-21 "Sem dados" regression)', () => {
    render(
      <KanbanBoard<Cliente, Etapa>
        columns={[]}
        getCardId={(c) => c.id}
        getCardStage={(c) => c.etapa_atual}
        renderCard={(c) => <span>{c.nome}</span>}
        onMove={() => {}}
        isLoading
      />,
    );
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.queryByText('Nenhuma etapa configurada.')).not.toBeInTheDocument();
  });

  // REGRESSION for the refetch-unmount bug: `useMoveCard`'s optimistic
  // mutation flips `isFetching` true again in `onSettled`, and a naive
  // consumer forwards that as `isLoading={isPending || isFetching}`. Before
  // this fix, `if (isLoading) return loadingState` unmounted the ENTIRE
  // board — every card, every column — on every single drag, even though
  // `columns` already held real data. This test constructs exactly that
  // state directly (`columns` populated + `isLoading` true) without needing
  // a live query mock, and proves the board keeps rendering.
  it('REGRESSION: does not unmount already-rendered cards when isLoading flips true again (background refetch)', () => {
    render(
      <KanbanBoard<Cliente, Etapa>
        columns={erpColumns()}
        getCardId={(c) => c.id}
        getCardStage={(c) => c.etapa_atual}
        renderCard={(c) => <span>{c.nome}</span>}
        onMove={() => {}}
        isLoading
      />,
    );
    expect(screen.getByText('Ana')).toBeInTheDocument();
    expect(screen.getByText('Bruno')).toBeInTheDocument();
    // Scoped to the loading skeleton's own label — `@dnd-kit`'s DndContext
    // renders its own `role="status"` aria-live region for accessibility
    // announcements, unrelated to this organ's loading state.
    expect(screen.queryByRole('status', { name: 'Carregando quadro' })).not.toBeInTheDocument();
  });

  it('shows the error state', () => {
    render(
      <KanbanBoard<Cliente, Etapa>
        columns={erpColumns()}
        getCardId={(c) => c.id}
        getCardStage={(c) => c.etapa_atual}
        renderCard={(c) => <span>{c.nome}</span>}
        onMove={() => {}}
        error={new Error('falhou')}
      />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('falhou');
  });

  it('shows the board-level empty state when there are no stages at all', () => {
    render(
      <KanbanBoard<Cliente, Etapa>
        columns={[]}
        getCardId={(c) => c.id}
        getCardStage={(c) => c.etapa_atual}
        renderCard={(c) => <span>{c.nome}</span>}
        onMove={() => {}}
      />,
    );
    expect(screen.getByText('Nenhuma etapa configurada.')).toBeInTheDocument();
  });
});

describe('computeMove — the move-resolution logic behind onMove', () => {
  it('erp-shaped: resolves a cross-column drop onto the destination column container', () => {
    const columns = erpColumns();
    const result = computeMove(
      columns,
      (c) => c.id,
      (c) => c.etapa_atual,
      'c1', // Ana, currently in "novo"
      'proposta', // dropped on the empty "proposta" column's droppable zone
    );
    expect(result).toEqual({ fromStage: 'novo', toStage: 'proposta', toIndex: 0 });
  });

  it('erp-shaped: resolves a cross-column drop onto a sibling card', () => {
    const columns = erpColumns();
    const result = computeMove(
      columns,
      (c) => c.id,
      (c) => c.etapa_atual,
      'c1', // Ana, currently in "novo"
      'c2', // dropped onto Bruno's card, in "contato"
    );
    expect(result).toEqual({ fromStage: 'novo', toStage: 'contato', toIndex: 0 });
  });

  it('orbity-shaped: resolves a within-column reorder (index change, same stage)', () => {
    const columns = orbityColumns();
    // Diego (index 0 in stage-2) dropped onto Eva (index 1) → moves to index 1.
    const result = computeMove(
      columns,
      (l) => l.id,
      (l) => l.stage_id,
      'l2',
      'l3',
    );
    expect(result).toEqual({ fromStage: 'stage-2', toStage: 'stage-2', toIndex: 1 });
  });

  it('orbity-shaped: no-op when a card is dropped back onto itself', () => {
    const columns = orbityColumns();
    const result = computeMove(
      columns,
      (l) => l.id,
      (l) => l.stage_id,
      'l1',
      'l1', // dnd-kit reports over === active when released without moving
    );
    expect(result).toBeNull();
  });

  it('returns null when the active card cannot be found (defensive — dnd-kit reported a stale id)', () => {
    const columns = erpColumns();
    const result = computeMove(columns, (c) => c.id, (c) => c.etapa_atual, 'does-not-exist', 'novo');
    expect(result).toBeNull();
  });
});
