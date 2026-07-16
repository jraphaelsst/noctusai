/**
 * `<KanbanCard/>` — the drag-wiring wrapper. Card *content* is always the
 * consumer's own component (passed as `children`); this wrapper only owns
 * the `@dnd-kit/sortable` plumbing (ref, transform style, a11y attributes,
 * pointer + keyboard listeners) so the consumer's card component never
 * needs to import `@dnd-kit/*` itself.
 */
import type { ReactNode } from 'react';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

export interface KanbanCardProps {
  /** The card's stable id — must match `getCardId(card)` in the board. */
  id: string;
  children: ReactNode;
  className?: string;
}

export function KanbanCard({ id, children, className }: KanbanCardProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id,
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      className={className}
      data-kanban-card-id={id}
    >
      {children}
    </div>
  );
}
