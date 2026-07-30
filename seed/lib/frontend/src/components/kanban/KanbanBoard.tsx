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
 * The organ owns: sensors (pointer + KEYBOARD — accessibility is not
 * optional), the droppable columns, the drag overlay, and computing
 * `(cardId, fromStage, toStage, toIndex)` for `onMove`. Card *rendering*
 * (and the actual mutation/API call) stay the consumer's job — the organ
 * never imports anything domain-specific.
 *
 * States: `isLoading` → `loadingState` (default: column skeletons).
 * `error` → `errorState`. `columns.length === 0` → `emptyState` (no stages
 * configured at all — distinct from an individual empty column, which
 * `KanbanColumn` handles on its own).
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
import { useMemo, useState, type ReactNode } from 'react';
import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  closestCorners,
  useSensor,
  useSensors,
  type CollisionDetection,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core';
import { sortableKeyboardCoordinates } from '@dnd-kit/sortable';
import { KanbanColumn } from './KanbanColumn';
import { computeMove } from './computeMove';
import type { KanbanCardRenderState, KanbanColumnData, KanbanOnMove, KanbanStage } from './types';

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
  renderColumnHeader?: (stage: KanbanStage<TStageId>, cards: TCard[]) => ReactNode;

  collisionDetection?: CollisionDetection;
  className?: string;
  columnClassName?: string;
  cardClassName?: string;
}

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
  collisionDetection = closestCorners,
  className,
  columnClassName,
  cardClassName,
}: KanbanBoardProps<TCard, TStageId>) {
  const [activeId, setActiveId] = useState<string | null>(null);

  // Keyboard sensor keeps the board operable without a pointer — dragging via
  // Tab-to-focus + Space-to-lift + Arrow-to-move + Space-to-drop. Pointer
  // sensor requires a small activation distance so a plain click (e.g. a
  // button inside the card) isn't swallowed as a drag start.
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const allCards = useMemo(() => columns.flatMap((c) => c.cards), [columns]);
  const activeCard = useMemo(
    () => (activeId ? allCards.find((c) => getCardId(c) === activeId) : undefined),
    [activeId, allCards, getCardId],
  );

  function handleDragStart(event: DragStartEvent) {
    setActiveId(event.active.id as string);
  }

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    setActiveId(null);
    if (!over) return;

    const cardId = active.id as string;
    const result = computeMove(columns, getCardId, getCardStage, cardId, over.id as string);
    if (!result) return;

    onMove(cardId, result.fromStage, result.toStage, result.toIndex);
  }

  if (isLoading) {
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
      collisionDetection={collisionDetection}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
    >
      <div className={className ?? 'flex gap-4 overflow-x-auto pb-4'}>
        {columns.map((column) => (
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
        ))}
      </div>

      <DragOverlay>
        {activeCard ? (
          <div className="rotate-3 scale-105">{renderCard(activeCard, { isDragging: true })}</div>
        ) : null}
      </DragOverlay>
    </DndContext>
  );
}
