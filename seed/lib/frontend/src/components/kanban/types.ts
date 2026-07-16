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
