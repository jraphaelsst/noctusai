/**
 * KanbanBoard organ — canonical drag-and-drop board.
 *
 * Usage:
 *   import { KanbanBoard, KanbanColumn, KanbanCard } from "@noctusai/lib/components";
 *   import type { KanbanColumnData, KanbanStage, KanbanOnMove } from "@noctusai/lib/components";
 */
export { KanbanBoard, kanbanCollisionDetection } from './KanbanBoard';
export type { KanbanBoardProps } from './KanbanBoard';

export { KanbanColumn } from './KanbanColumn';
export type { KanbanColumnProps, KanbanColumnSortableBinding } from './KanbanColumn';

export { SortableKanbanColumn } from './SortableKanbanColumn';
export type { SortableKanbanColumnProps } from './SortableKanbanColumn';

export { KanbanCard } from './KanbanCard';
export type { KanbanCardProps } from './KanbanCard';

export {
  computeMove,
  computeColumnReorder,
  columnDndId,
  stageIdFromColumnDndId,
  KANBAN_COLUMN_DND_PREFIX,
} from './computeMove';

export {
  useKanbanSensors,
  KANBAN_MOUSE_ACTIVATION,
  KANBAN_MOUSE_DISTANCE_PX,
  KANBAN_TOUCH_ACTIVATION,
} from './sensors';
export type { ComputeMoveResult } from './computeMove';

export type {
  KanbanStage,
  KanbanColumnData,
  KanbanCardRenderState,
  KanbanOnMove,
  KanbanOnColumnReorder,
  KanbanColumnHeaderContext,
} from './types';
