/**
 * `<KanbanColumn/>` — one droppable stage column. Owns the droppable zone
 * (`useDroppable`, id = the stage id — the drop target when a column has
 * zero cards) and the `SortableContext` for within-column reordering.
 * Header + empty-state rendering are consumer-overridable; the default
 * header just shows the stage label + a count badge.
 */
import type { ReactNode } from 'react';
import { useDroppable } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { KanbanCard } from './KanbanCard';
import type { KanbanCardRenderState, KanbanColumnData } from './types';

export interface KanbanColumnProps<TCard, TStageId extends string = string> {
  column: KanbanColumnData<TCard, TStageId>;
  getCardId: (card: TCard) => string;
  renderCard: (card: TCard, state: KanbanCardRenderState) => ReactNode;
  /** Override the column header. Receives the stage + its current cards. */
  renderHeader?: (stage: KanbanColumnData<TCard, TStageId>['stage'], cards: TCard[]) => ReactNode;
  /** Override the "no cards" message for this column. */
  emptyState?: ReactNode;
  className?: string;
  cardClassName?: string;
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
  className,
  cardClassName,
}: KanbanColumnProps<TCard, TStageId>) {
  const { stage, cards } = column;
  const { setNodeRef } = useDroppable({ id: stage.id });
  const cardIds = cards.map(getCardId);

  return (
    <div className={className ?? 'flex-shrink-0 w-80'}>
      {renderHeader ? renderHeader(stage, cards) : <DefaultHeader label={stage.label} count={cards.length} />}

      <div ref={setNodeRef} className="flex-1 min-h-[4rem]" data-kanban-column-id={stage.id}>
        <SortableContext items={cardIds} strategy={verticalListSortingStrategy}>
          {cards.map((card) => (
            <KanbanCard key={getCardId(card)} id={getCardId(card)} className={cardClassName}>
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
