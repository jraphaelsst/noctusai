/**
 * Shared types for the `KanbanBoard` organ.
 *
 * Generic over the card type AND the stage-id type — the organ never assumes
 * a domain vocabulary (no `etapa_atual`, no `stage_id` literal). A consumer
 * supplies field-access via `getCardId` / `getCardStage`, not by shaping its
 * data to match the organ. See `KB § PATTERNS/architect/seed-canonical-defaults.md`
 * — the organ is the canonical answer, not a generalization of consumer #1.
 */
import type { ReactNode } from 'react';

/** A single kanban stage/column identity — id + display label. */
export interface KanbanStage<TStageId extends string = string> {
  id: TStageId;
  label: string;
}

/** One column's data: the stage it represents + the cards currently in it. */
export interface KanbanColumnData<TCard, TStageId extends string = string> {
  stage: KanbanStage<TStageId>;
  cards: TCard[];
}

/** Render-state passed to `renderCard` so the consumer can style the dragged copy. */
export interface KanbanCardRenderState {
  isDragging: boolean;
}

/**
 * Fired when a card is dropped into a new position — cross-column OR
 * within the same column. `toIndex` is the card's new index inside
 * `toStage`'s column. The organ does NOT filter same-stage moves; a
 * consumer that only wants cross-column transitions (the ERP Funil's
 * current behavior) checks `fromStage !== toStage` itself before acting.
 */
export type KanbanOnMove<TStageId extends string = string> = (
  cardId: string,
  fromStage: TStageId,
  toStage: TStageId,
  toIndex: number,
) => void;

/**
 * Fired when the user drags a COLUMN to a new position. Receives the FULL new
 * column order (every rendered stage id), not a `(id, index)` pair — a partial
 * reorder forces every receiver to re-derive the rest, and two receivers
 * deriving differently is how column order flickers between users.
 */
export type KanbanOnColumnReorder<TStageId extends string = string> = (
  orderedStageIds: TStageId[],
) => void;

/**
 * Third argument of `renderColumnHeader`. Present only when columns are
 * drag-reorderable (`onColumnReorder` set); a consumer header that ignores it
 * still works — the whole header area is the drag handle.
 */
export interface KanbanColumnHeaderContext {
  /** True while THIS column is being dragged. */
  isColumnDragging: boolean;
  /** True when the board lets columns be dragged. */
  columnsReorderable: boolean;
}
