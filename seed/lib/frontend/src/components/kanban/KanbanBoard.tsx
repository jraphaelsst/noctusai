/**
 * `<KanbanBoard/>` — the canonical drag-and-drop board organ.
 *
 * Formalizes the N=3 kanban recurrence (`KB § PATTERNS/architect/
 * project-execution.md` — N=3+ MUST formalize): two independent hand-rolled
 * `@dnd-kit` boards existed before this organ (ERP `Funil` — cards =
 * `clientes`, stage field `etapa_atual`; Orbity CRM `Funil` — cards =
 * `leads`, stage field `stage_id`). This organ is generic over BOTH the card
 * type and the stage-id type: it takes `columns` pre-grouped by the
 * consumer's own query, plus `getCardId` / `getCardStage` accessors, so
 * neither consumer has to bend its domain vocabulary to fit the organ
 * (`KB § PATTERNS/architect/seed-canonical-defaults.md`).
 *
 * The organ owns: sensors (mouse + press-and-hold TOUCH + KEYBOARD — see
 * `sensors.ts`; accessibility and phones are not optional), the droppable
 * columns, the drag overlay, and computing `(cardId, fromStage, toStage,
 * toIndex)` for `onMove`. Card *rendering*
 * (and the actual mutation/API call) stay the consumer's job — the organ
 * never imports anything domain-specific.
 *
 * States: `isLoading` → `loadingState` (default: column skeletons) —
 * honoured ONLY while `columns` is still empty. `error` → `errorState`.
 * `columns.length === 0` → `emptyState` (no stages configured at all —
 * distinct from an individual empty column, which `KanbanColumn` handles
 * on its own).
 *
 * `isLoading` scoping is deliberate (`KB § PATTERNS/frontend/
 * lying-loading-state.md`): a consumer's `useMoveCard` is typically
 * optimistic, so its `onSettled` flips `isFetching` true on every drag —
 * if the board unmounted on that flip it would blank + re-mount on every
 * single move. Once `columns` holds real data the board never unmounts for
 * it again, so a consumer that still passes the broad `isPending ||
 * isFetching` (rather than scoping it to the empty case itself, as the
 * canonical `Funil.tsx` pattern does) is safe by construction here — no
 * consumer change required to pick up the fix.
 *
 * COLUMN REORDERING (opt-in via `onColumnReorder`): the columns become a
 * horizontal `SortableContext` INSIDE the one `DndContext` — never a second,
 * nested context, which is a reliable source of pointer-capture bugs. Drags
 * are discriminated by `active.data.current.type` (`'card'` | `'column'`), and
 * the collision detection is narrowed per drag kind so a card never "lands"
 * on a column's sortable wrapper and a column never lands on a card. Without
 * `onColumnReorder` none of this is mounted and the board is unchanged.
 *
 * `renderTrailingColumn` renders one extra non-draggable slot after the last
 * column (e.g. a "+ coluna" affordance), inside the same scroll container.
 *
 * Usage (erp-shaped data):
 * ```tsx
 * <KanbanBoard
 *   columns={colunas.map((c) => ({ stage: { id: c.etapa, label: ETAPAS_CONFIG[c.etapa].label }, cards: c.cards }))}
 *   getCardId={(c) => c.id}
 *   getCardStage={(c) => c.etapa_atual}
 *   renderCard={(cliente, { isDragging }) => <ClienteCard cliente={cliente} isDragging={isDragging} />}
 *   onMove={(id, from, to, toIndex) => { if (from !== to) moverCliente({ cliente_id: id, para_etapa: to, novo_indice: toIndex }); }}
 * />
 * ```
 *
 * Usage (orbity-shaped data):
 * ```tsx
 * <KanbanBoard
 *   columns={funilStages.map((fs) => ({ stage: { id: fs.stage.id, label: fs.stage.name }, cards: fs.leads }))}
 *   getCardId={(lead) => lead.id}
 *   getCardStage={(lead) => lead.stage_id ?? ''}
 *   renderCard={(lead) => <LeadCard lead={lead} />}
 *   onMove={(id, _from, to) => moveLeadStage.mutate({ id, stage_id: to })}
 * />
 * ```
 */
import { useCallback, useMemo, useState, type ReactNode } from 'react';
import {
  DndContext,
  DragOverlay,
  closestCenter,
  closestCorners,
  type CollisionDetection,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core';
import { SortableContext, horizontalListSortingStrategy } from '@dnd-kit/sortable';
import { KanbanColumn } from './KanbanColumn';
import { SortableKanbanColumn } from './SortableKanbanColumn';
import {
  columnDndId,
  computeColumnReorder,
  computeMove,
  stageIdFromColumnDndId,
} from './computeMove';
import { useKanbanSensors } from './sensors';
import type {
  KanbanCardRenderState,
  KanbanColumnData,
  KanbanColumnHeaderContext,
  KanbanOnColumnReorder,
  KanbanOnMove,
  KanbanStage,
} from './types';

/**
 * Narrow the droppables a drag may collide with to the ones of its own kind.
 *
 * With reorderable columns there are two families of droppables on the board:
 * column sortables (ids from `columnDndId`) and everything else (card
 * sortables + each column's card drop zone). A column drag must only ever
 * resolve against another column; a card drag must never resolve against a
 * column's sortable wrapper, which covers the entire column and would
 * otherwise win `closestCorners` over the cards inside it.
 */
export function kanbanCollisionDetection(cardDetection: CollisionDetection): CollisionDetection {
  return (args) => {
    const activeIsColumn = stageIdFromColumnDndId(String(args.active.id)) !== null;
    const droppableContainers = args.droppableContainers.filter(
      (container) => (stageIdFromColumnDndId(String(container.id)) !== null) === activeIsColumn,
    );
    return activeIsColumn
      ? closestCenter({ ...args, droppableContainers })
      : cardDetection({ ...args, droppableContainers });
  };
}

export interface KanbanBoardProps<TCard, TStageId extends string = string> {
  columns: KanbanColumnData<TCard, TStageId>[];
  getCardId: (card: TCard) => string;
  getCardStage: (card: TCard) => TStageId;
  renderCard: (card: TCard, state: KanbanCardRenderState) => ReactNode;
  onMove: KanbanOnMove<TStageId>;
  /**
   * A genuine card click — press and release without a drag. Omit and cards
   * are drag-only. The drag/click discrimination lives in `KanbanCard`; see
   * its header for why a naive `onClick` fires on every completed drag.
   */
  onCardActivate?: (card: TCard) => void;

  isLoading?: boolean;
  error?: unknown;
  loadingState?: ReactNode;
  errorState?: ReactNode;
  emptyState?: ReactNode;
  columnEmptyState?: (stage: KanbanStage<TStageId>) => ReactNode;
  renderColumnHeader?: (
    stage: KanbanStage<TStageId>,
    cards: TCard[],
    context: KanbanColumnHeaderContext,
  ) => ReactNode;

  /**
   * Opt-in COLUMN drag-reorder. Receives the full new stage-id order. Omit and
   * columns are fixed (the historical behaviour, byte-identical DOM).
   */
  onColumnReorder?: KanbanOnColumnReorder<TStageId>;
  /** One extra non-draggable slot after the last column (e.g. "+ coluna"). */
  renderTrailingColumn?: () => ReactNode;

  collisionDetection?: CollisionDetection;
  className?: string;
  columnClassName?: string;
  cardClassName?: string;
}

/** Default scroll container. See the render comment for the mobile classes. */
export const DEFAULT_BOARD_CLASS =
  'flex gap-4 overflow-x-auto overscroll-x-contain min-w-0 max-w-full pb-4';

function DefaultLoadingState() {
  return (
    <div className="flex gap-4 overflow-x-auto pb-4" role="status" aria-label="Carregando quadro">
      {[1, 2, 3, 4].map((i) => (
        <div key={i} className="w-80 h-96 flex-shrink-0 rounded-md bg-muted animate-pulse" />
      ))}
    </div>
  );
}

function DefaultErrorState({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : 'Não foi possível carregar o quadro.';
  return (
    <div role="alert" className="text-center text-sm text-destructive py-12">
      {message}
    </div>
  );
}

function DefaultEmptyState() {
  return (
    <div className="text-center text-muted-foreground text-sm py-12">
      Nenhuma etapa configurada.
    </div>
  );
}

export function KanbanBoard<TCard, TStageId extends string = string>({
  columns,
  getCardId,
  getCardStage,
  renderCard,
  onMove,
  onCardActivate,
  isLoading = false,
  error,
  loadingState,
  errorState,
  emptyState,
  columnEmptyState,
  renderColumnHeader,
  onColumnReorder,
  renderTrailingColumn,
  collisionDetection = closestCorners,
  className,
  columnClassName,
  cardClassName,
}: KanbanBoardProps<TCard, TStageId>) {
  const [activeId, setActiveId] = useState<string | null>(null);

  // Mouse (8px distance) + TOUCH (press-and-hold, so a swipe scrolls the board
  // instead of dragging a card) + keyboard. See `sensors.ts`.
  const sensors = useKanbanSensors();

  const columnsReorderable = Boolean(onColumnReorder);
  const effectiveCollision = useMemo(
    () => (columnsReorderable ? kanbanCollisionDetection(collisionDetection) : collisionDetection),
    [columnsReorderable, collisionDetection],
  );
  const stageIds = useMemo(() => columns.map((c) => c.stage.id), [columns]);
  const columnSortableIds = useMemo(() => stageIds.map(columnDndId), [stageIds]);
  const activeColumn = useMemo(() => {
    const stageId = activeId ? stageIdFromColumnDndId(activeId) : null;
    return stageId ? columns.find((c) => c.stage.id === stageId) : undefined;
  }, [activeId, columns]);

  const allCards = useMemo(() => columns.flatMap((c) => c.cards), [columns]);
  const activeCard = useMemo(
    () => (activeId ? allCards.find((c) => getCardId(c) === activeId) : undefined),
    [activeId, allCards, getCardId],
  );

  function handleDragStart(event: DragStartEvent) {
    setActiveId(event.active.id as string);
  }

  const handleDragEnd = useCallback((event: DragEndEvent) => {
    const { active, over } = event;
    setActiveId(null);
    if (!over) return;

    // A COLUMN drag: resolve the new full order and hand it over. Discriminate
    // on `data.type` first, falling back to the id prefix for robustness.
    const isColumnDrag =
      active.data.current?.type === 'column' || stageIdFromColumnDndId(String(active.id)) !== null;
    if (isColumnDrag) {
      if (!onColumnReorder) return;
      const next = computeColumnReorder(stageIds, String(active.id), String(over.id));
      if (next) onColumnReorder(next);
      return;
    }

    const cardId = active.id as string;
    const result = computeMove(columns, getCardId, getCardStage, cardId, over.id as string);
    if (!result) return;

    onMove(cardId, result.fromStage, result.toStage, result.toIndex);
  }, [columns, getCardId, getCardStage, onColumnReorder, onMove, stageIds]);

  // Gate on `isLoading && columns.length === 0`, never bare `isLoading`:
  // once real columns exist, a background refetch (e.g. `useMoveCard`'s
  // optimistic `onSettled` invalidation) must never unmount the board — see
  // the file header. This also preserves the 2026-07-21 empty-over-loading
  // regression fix: when `columns` is genuinely empty, `isLoading` still
  // wins over the `emptyState` branch below.
  if (isLoading && columns.length === 0) {
    return <>{loadingState ?? <DefaultLoadingState />}</>;
  }

  if (error) {
    return <>{errorState ?? <DefaultErrorState error={error} />}</>;
  }

  if (columns.length === 0) {
    return <>{emptyState ?? <DefaultEmptyState />}</>;
  }

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={effectiveCollision}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
    >
      {/*
        The board scrolls horizontally INSIDE this container, never the page:
        `min-w-0 max-w-full` keep it from growing to its content width when it
        is itself a flex item (the phone-width page-overflow class), and
        `overscroll-x-contain` stops a horizontal swipe at the board's edge
        from turning into the browser's back/forward gesture.
      */}
      <div className={className ?? DEFAULT_BOARD_CLASS}>
        {columnsReorderable ? (
          <SortableContext items={columnSortableIds} strategy={horizontalListSortingStrategy}>
            {columns.map((column) => (
              <SortableKanbanColumn
                key={column.stage.id}
                column={column}
                getCardId={getCardId}
                renderCard={renderCard}
                onCardActivate={onCardActivate}
                renderHeader={renderColumnHeader}
                emptyState={columnEmptyState ? columnEmptyState(column.stage) : undefined}
                className={columnClassName}
                cardClassName={cardClassName}
              />
            ))}
          </SortableContext>
        ) : (
          columns.map((column) => (
            <KanbanColumn
              key={column.stage.id}
              column={column}
              getCardId={getCardId}
              renderCard={renderCard}
              onCardActivate={onCardActivate}
              renderHeader={renderColumnHeader}
              emptyState={columnEmptyState ? columnEmptyState(column.stage) : undefined}
              className={columnClassName}
              cardClassName={cardClassName}
            />
          ))
        )}
        {renderTrailingColumn ? renderTrailingColumn() : null}
      </div>

      <DragOverlay>
        {activeCard ? (
          <div className="rotate-3 scale-105">{renderCard(activeCard, { isDragging: true })}</div>
        ) : activeColumn ? (
          // A column in flight shows its header only — the cards stay put in
          // the (translucent) original until the drop lands.
          <div className={columnClassName ?? 'flex-shrink-0 w-80'} data-kanban-column-overlay={activeColumn.stage.id}>
            {renderColumnHeader
              ? renderColumnHeader(activeColumn.stage, activeColumn.cards, {
                  isColumnDragging: true,
                  columnsReorderable: true,
                })
              : (
                <div className="rounded-md border bg-card px-3 py-2 font-semibold text-sm shadow">
                  {activeColumn.stage.label}
                </div>
              )}
          </div>
        ) : null}
      </DragOverlay>
    </DndContext>
  );
}
