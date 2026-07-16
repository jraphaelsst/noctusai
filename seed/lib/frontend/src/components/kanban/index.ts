/**
 * KanbanBoard organ — canonical drag-and-drop board.
 *
 * Usage:
 *   import { KanbanBoard, KanbanColumn, KanbanCard } from "@noctusai/lib/components";
 *   import type { KanbanColumnData, KanbanStage, KanbanOnMove } from "@noctusai/lib/components";
 */
export { KanbanBoard } from './KanbanBoard';
export type { KanbanBoardProps } from './KanbanBoard';

export { KanbanColumn } from './KanbanColumn';
export type { KanbanColumnProps } from './KanbanColumn';

export { KanbanCard } from './KanbanCard';
export type { KanbanCardProps } from './KanbanCard';

export { computeMove } from './computeMove';
export type { ComputeMoveResult } from './computeMove';

export type {
  KanbanStage,
  KanbanColumnData,
  KanbanCardRenderState,
  KanbanOnMove,
} from './types';
