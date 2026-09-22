/**
 * Column drag-reorder + mobile sensors for the `KanbanBoard` organ.
 *
 * Drag itself is not simulated — `@dnd-kit` sensors need layout geometry jsdom
 * does not compute (`reference_lib_frontend_vitest_render_harness_gap`). What
 * is pinned instead is every DECISION the board makes on a drag:
 *  - `computeMove` ignores column drags and maps a column-wrapper `over` to its
 *    stage (the guard that keeps card moves and column moves apart);
 *  - `computeColumnReorder` produces the full new order;
 *  - `kanbanCollisionDetection` narrows collisions to the drag's own kind;
 *  - the sensor set is mouse (distance) + touch (press-and-hold) + keyboard;
 *  - column sortables mount ONLY when `onColumnReorder` is passed.
 */
/// <reference types="@testing-library/jest-dom" />
import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, cleanup, renderHook } from '@testing-library/react';
import {
  KeyboardSensor,
  MouseSensor,
  TouchSensor,
  type Collision,
  type CollisionDetection,
} from '@dnd-kit/core';

import { KanbanBoard, kanbanCollisionDetection, DEFAULT_BOARD_CLASS } from './KanbanBoard';
import {
  KANBAN_COLUMN_DND_PREFIX,
  columnDndId,
  computeColumnReorder,
  computeMove,
  stageIdFromColumnDndId,
} from './computeMove';
import {
  KANBAN_MOUSE_ACTIVATION,
  KANBAN_MOUSE_DISTANCE_PX,
  KANBAN_TOUCH_ACTIVATION,
  useKanbanSensors,
} from './sensors';
import type { KanbanColumnData } from './types';

afterEach(() => cleanup());

interface Card {
  id: string;
  stage: string;
}

function columns(): KanbanColumnData<Card>[] {
  return [
    { stage: { id: 'a', label: 'A' }, cards: [{ id: 'c1', stage: 'a' }] },
    { stage: { id: 'b', label: 'B' }, cards: [{ id: 'c2', stage: 'b' }] },
    { stage: { id: 'c', label: 'C' }, cards: [] },
  ];
}

const getId = (c: Card) => c.id;
const getStage = (c: Card) => c.stage;

describe('column dnd ids', () => {
  it('round-trips a stage id and rejects non-column ids', () => {
    expect(columnDndId('a')).toBe(`${KANBAN_COLUMN_DND_PREFIX}a`);
    expect(stageIdFromColumnDndId(columnDndId('a'))).toBe('a');
    expect(stageIdFromColumnDndId('a')).toBeNull();
    expect(stageIdFromColumnDndId('c1')).toBeNull();
  });
});

describe('computeMove — column-drag guard', () => {
  it('returns null when the ACTIVE id is a column (a column drag is never a card move)', () => {
    expect(computeMove(columns(), getId, getStage, columnDndId('a'), 'b')).toBeNull();
    expect(computeMove(columns(), getId, getStage, columnDndId('a'), columnDndId('b'))).toBeNull();
  });

  it('treats a card dropped on a column WRAPPER as dropped into that column', () => {
    expect(computeMove(columns(), getId, getStage, 'c1', columnDndId('c'))).toEqual({
      fromStage: 'a',
      toStage: 'c',
      toIndex: 0,
    });
  });

  it('still resolves plain card-on-card and card-on-zone moves unchanged', () => {
    expect(computeMove(columns(), getId, getStage, 'c1', 'c2')).toEqual({
      fromStage: 'a',
      toStage: 'b',
      toIndex: 0,
    });
    expect(computeMove(columns(), getId, getStage, 'c1', 'b')).toEqual({
      fromStage: 'a',
      toStage: 'b',
      toIndex: 1,
    });
  });
});

describe('computeColumnReorder', () => {
  const ids = ['a', 'b', 'c'];

  it('moves a column forward and backward, returning the FULL order', () => {
    expect(computeColumnReorder(ids, columnDndId('a'), columnDndId('c'))).toEqual(['b', 'c', 'a']);
    expect(computeColumnReorder(ids, columnDndId('c'), columnDndId('a'))).toEqual(['c', 'a', 'b']);
  });

  it('accepts raw stage ids too', () => {
    expect(computeColumnReorder(ids, 'b', 'a')).toEqual(['b', 'a', 'c']);
  });

  it('returns null for a no-op or an unknown id', () => {
    expect(computeColumnReorder(ids, columnDndId('b'), columnDndId('b'))).toBeNull();
    expect(computeColumnReorder(ids, columnDndId('zz'), columnDndId('a'))).toBeNull();
    expect(computeColumnReorder(ids, 'c1', columnDndId('a'))).toBeNull();
  });

  it('does not mutate its input', () => {
    const input = ['a', 'b', 'c'];
    computeColumnReorder(input, 'a', 'c');
    expect(input).toEqual(['a', 'b', 'c']);
  });
});

describe('kanbanCollisionDetection', () => {
  const containers = [
    { id: columnDndId('a') },
    { id: columnDndId('b') },
    { id: 'a' },
    { id: 'c1' },
  ] as any[];

  function spyDetection() {
    const seen: string[][] = [];
    const detection: CollisionDetection = (args) => {
      seen.push(args.droppableContainers.map((c) => String(c.id)));
      return [] as Collision[];
    };
    return { detection, seen };
  }

  it('lets a CARD drag collide only with cards and card drop zones', () => {
    const { detection, seen } = spyDetection();
    kanbanCollisionDetection(detection)({
      active: { id: 'c1' },
      droppableContainers: containers,
      droppableRects: new Map(),
      collisionRect: { top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0 },
      pointerCoordinates: null,
    } as any);
    expect(seen[0]).toEqual(['a', 'c1']);
  });

  it('lets a COLUMN drag collide only with other columns (never the card detection)', () => {
    const { detection, seen } = spyDetection();
    const result = kanbanCollisionDetection(detection)({
      active: { id: columnDndId('a') },
      droppableContainers: containers,
      droppableRects: new Map(),
      collisionRect: { top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0 },
      pointerCoordinates: null,
    } as any);
    expect(seen).toHaveLength(0);
    expect(Array.isArray(result)).toBe(true);
  });
});

describe('touch sensor config (mobile)', () => {
  it('uses mouse distance + touch press-and-hold + keyboard', () => {
    const { result } = renderHook(() => useKanbanSensors());
    const sensors = result.current.map((d) => d.sensor);
    expect(sensors).toEqual([MouseSensor, TouchSensor, KeyboardSensor]);
    expect(result.current[0].options).toMatchObject({ activationConstraint: KANBAN_MOUSE_ACTIVATION });
    expect(result.current[1].options).toMatchObject({ activationConstraint: KANBAN_TOUCH_ACTIVATION });
  });

  it('keeps desktop at 8px and gives touch a real hold + jitter tolerance', () => {
    expect(KANBAN_MOUSE_DISTANCE_PX).toBe(8);
    expect(KANBAN_MOUSE_ACTIVATION).toEqual({ distance: 8 });
    // A delay (not a distance) is what lets a vertical swipe scroll instead of drag.
    expect(KANBAN_TOUCH_ACTIVATION.delay).toBeGreaterThanOrEqual(150);
    expect(KANBAN_TOUCH_ACTIVATION.tolerance).toBeGreaterThan(0);
    expect('distance' in KANBAN_TOUCH_ACTIVATION).toBe(false);
  });

  it('scrolls horizontally inside its own container, never the page', () => {
    render(
      <KanbanBoard columns={columns()} getCardId={getId} getCardStage={getStage} renderCard={(c) => <span>{c.id}</span>} onMove={() => {}} />,
    );
    const scroller = document.querySelector('[data-kanban-column-id="a"]')!.parentElement!.parentElement!;
    expect(scroller.className).toBe(DEFAULT_BOARD_CLASS);
    expect(DEFAULT_BOARD_CLASS).toContain('overflow-x-auto');
    expect(DEFAULT_BOARD_CLASS).toContain('max-w-full');
    expect(DEFAULT_BOARD_CLASS).toContain('min-w-0');
  });
});

describe('KanbanBoard — column reorder is opt-in', () => {
  function renderBoard(extra: Record<string, unknown> = {}) {
    return render(
      <KanbanBoard
        columns={columns()}
        getCardId={getId}
        getCardStage={getStage}
        renderCard={(c) => <span>{c.id}</span>}
        onMove={() => {}}
        {...extra}
      />,
    );
  }

  it('mounts NO column handles without onColumnReorder (existing consumers unchanged)', () => {
    renderBoard();
    expect(document.querySelectorAll('[data-kanban-column-handle]')).toHaveLength(0);
    expect(document.querySelectorAll('[data-kanban-column-sortable]')).toHaveLength(0);
  });

  it('makes every column header a drag handle with onColumnReorder', () => {
    renderBoard({ onColumnReorder: vi.fn() });
    const handles = document.querySelectorAll('[data-kanban-column-handle]');
    expect(handles).toHaveLength(3);
    // dnd-kit sortable attributes: keyboard-focusable, announced as sortable.
    expect(handles[0]).toHaveAttribute('tabindex', '0');
    expect(handles[0]).toHaveAttribute('aria-roledescription', 'sortable');
  });

  it('passes the header context to renderColumnHeader', () => {
    const renderColumnHeader = vi.fn(() => <span>h</span>);
    renderBoard({ onColumnReorder: vi.fn(), renderColumnHeader });
    expect(renderColumnHeader).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'a' }),
      expect.any(Array),
      { isColumnDragging: false, columnsReorderable: true },
    );
  });

  it('renders the trailing column after the last column', () => {
    renderBoard({ renderTrailingColumn: () => <div data-testid="trailing">+ coluna</div> });
    const trailing = screen.getByTestId('trailing');
    const lastColumn = document.querySelector('[data-kanban-column-id="c"]')!.parentElement!;
    expect(lastColumn.nextElementSibling).toBe(trailing);
  });
});
