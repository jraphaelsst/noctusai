/**
 * `<SortableKanbanColumn/>` — a `KanbanColumn` that can itself be dragged to a
 * new position among its siblings.
 *
 * A separate component (rather than a flag on `KanbanColumn`) because
 * `useSortable` is a hook: calling it conditionally is illegal, and calling it
 * unconditionally would register every column as a sortable on boards that
 * never asked for column reordering — changing their collision surface. Boards
 * without `onColumnReorder` never mount this.
 *
 * The column registers under `columnDndId(stage.id)` with `data.type ===
 * 'column'`; its card drop zone keeps the raw stage id. See `computeMove.ts`
 * for why the two ids must differ.
 */
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

import { KanbanColumn, type KanbanColumnProps } from './KanbanColumn';
import { columnDndId } from './computeMove';

export type SortableKanbanColumnProps<TCard, TStageId extends string = string> = Omit<
  KanbanColumnProps<TCard, TStageId>,
  'sortable'
>;

export function SortableKanbanColumn<TCard, TStageId extends string = string>(
  props: SortableKanbanColumnProps<TCard, TStageId>,
) {
  const stageId = props.column.stage.id;
  const {
    attributes,
    listeners,
    setNodeRef,
    setActivatorNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: columnDndId(stageId), data: { type: 'column', stageId } });

  return (
    <KanbanColumn
      {...props}
      sortable={{
        setNodeRef,
        setActivatorNodeRef,
        // Translate only — a column swapping with a narrower/wider neighbour
        // must not be scaled to its size.
        style: {
          transform: CSS.Translate.toString(transform),
          transition,
          opacity: isDragging ? 0.5 : 1,
        },
        handleProps: { ...attributes, ...listeners },
        isDragging,
      }}
    />
  );
}
