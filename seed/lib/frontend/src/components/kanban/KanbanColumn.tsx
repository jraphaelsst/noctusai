/**
 * `<KanbanColumn/>` — one droppable stage column. Owns the droppable zone
 * (`useDroppable`, id = the stage id — the drop target when a column has
 * zero cards) and the `SortableContext` for within-column reordering.
 * Header + empty-state rendering are consumer-overridable; the default
 * header just shows the stage label + a count badge.
 *
 * When the board makes columns drag-reorderable it passes `sortable` (from
 * `SortableKanbanColumn`): the root gets the sortable ref + transform and the
 * header area becomes the drag handle. Without `sortable` the rendered DOM is
 * exactly what it always was — reordering is opt-in per board.
 */
import type { CSSProperties, ReactNode } from 'react';
import { useDroppable } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { KanbanCard } from './KanbanCard';
import type {
  KanbanCardRenderState,
  KanbanColumnData,
  KanbanColumnHeaderContext,
} from './types';

/** Sortable wiring handed down by `SortableKanbanColumn`. */
export interface KanbanColumnSortableBinding {
  setNodeRef: (element: HTMLElement | null) => void;
  setActivatorNodeRef: (element: HTMLElement | null) => void;
  style: CSSProperties;
  /** dnd-kit `attributes` + `listeners`, spread on the header handle. */
  handleProps: Record<string, unknown>;
  isDragging: boolean;
}

export interface KanbanColumnProps<TCard, TStageId extends string = string> {
  column: KanbanColumnData<TCard, TStageId>;
  getCardId: (card: TCard) => string;
  renderCard: (card: TCard, state: KanbanCardRenderState) => ReactNode;
  /**
   * Override the column header. Receives the stage + its current cards, and a
   * context saying whether the column is draggable / being dragged.
   */
  renderHeader?: (
    stage: KanbanColumnData<TCard, TStageId>['stage'],
    cards: TCard[],
    context: KanbanColumnHeaderContext,
  ) => ReactNode;
  /** Override the "no cards" message for this column. */
  emptyState?: ReactNode;
  /** Genuine card click (not a drag). See `KanbanCard`'s `onActivate`. */
  onCardActivate?: (card: TCard) => void;
  className?: string;
  cardClassName?: string;
  /** Present only when the board's columns are drag-reorderable. */
  sortable?: KanbanColumnSortableBinding;
}

function DefaultHeader({ label, count }: { label: string; count: number }) {
  return (
    <div className="flex items-center justify-between mb-2 px-1">
      <h3 className="font-semibold text-sm">{label}</h3>
      <span className="inline-flex items-center justify-center rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
        {count}
      </span>
    </div>
  );
}

export function KanbanColumn<TCard, TStageId extends string = string>({
  column,
  getCardId,
  renderCard,
  renderHeader,
  emptyState,
  onCardActivate,
  className,
  cardClassName,
  sortable,
}: KanbanColumnProps<TCard, TStageId>) {
  const { stage, cards } = column;
  const { setNodeRef } = useDroppable({ id: stage.id, data: { type: 'column-body', stageId: stage.id } });
  const cardIds = cards.map(getCardId);

  const headerContext: KanbanColumnHeaderContext = {
    isColumnDragging: sortable?.isDragging ?? false,
    columnsReorderable: Boolean(sortable),
  };
  const header = renderHeader ? (
    renderHeader(stage, cards, headerContext)
  ) : (
    <DefaultHeader label={stage.label} count={cards.length} />
  );

  return (
    <div
      ref={sortable?.setNodeRef}
      style={sortable?.style}
      className={className ?? 'flex-shrink-0 w-80'}
      data-kanban-column-sortable={sortable ? stage.id : undefined}
    >
      {sortable ? (
        // The whole header area is the column's drag handle — a consumer
        // header needs no dnd-kit wiring of its own. Registered as the
        // ACTIVATOR node so a keyboard Enter/Space inside a control in the
        // header (a menu button, a rename input) is NOT read as "lift the
        // column": dnd-kit ignores keyboard activation whose target is not the
        // activator itself.
        <div
          ref={sortable.setActivatorNodeRef}
          {...sortable.handleProps}
          className="cursor-grab active:cursor-grabbing"
          data-kanban-column-handle={stage.id}
        >
          {header}
        </div>
      ) : (
        header
      )}

      <div ref={setNodeRef} className="flex-1 min-h-[4rem]" data-kanban-column-id={stage.id}>
        <SortableContext items={cardIds} strategy={verticalListSortingStrategy}>
          {cards.map((card) => (
            <KanbanCard
              key={getCardId(card)}
              id={getCardId(card)}
              className={cardClassName}
              onActivate={onCardActivate ? () => onCardActivate(card) : undefined}
            >
              {renderCard(card, { isDragging: false })}
            </KanbanCard>
          ))}
        </SortableContext>

        {cards.length === 0 &&
          (emptyState ?? (
            <div className="text-center text-muted-foreground text-sm py-8">
              Nenhum item nesta etapa
            </div>
          ))}
      </div>
    </div>
  );
}
