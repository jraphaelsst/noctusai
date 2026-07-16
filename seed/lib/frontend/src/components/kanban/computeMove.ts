/**
 * Pure move-resolution logic, extracted out of `KanbanBoard` so it is
 * unit-testable without simulating real `@dnd-kit` pointer/keyboard drag
 * events in jsdom (dnd-kit's sensors depend on real layout geometry —
 * `getBoundingClientRect` — which jsdom does not compute; see
 * `reference_lib_frontend_vitest_render_harness_gap` in memory). Testing
 * this function directly proves the generality claim (works against
 * differently-shaped card types) without fighting the harness gap.
 *
 * Given the id dnd-kit reports as `active` and the id it reports as `over`,
 * resolve `(fromStage, toStage, toIndex)` — or `null` if nothing actually
 * moved (dropped back onto its own slot).
 */
import type { KanbanColumnData } from './types';

export interface ComputeMoveResult<TStageId extends string = string> {
  fromStage: TStageId;
  toStage: TStageId;
  toIndex: number;
}

export function computeMove<TCard, TStageId extends string = string>(
  columns: KanbanColumnData<TCard, TStageId>[],
  getCardId: (card: TCard) => string,
  getCardStage: (card: TCard) => TStageId,
  activeCardId: string,
  overId: string,
): ComputeMoveResult<TStageId> | null {
  const allCards = columns.flatMap((c) => c.cards);
  const activeCard = allCards.find((c) => getCardId(c) === activeCardId);
  if (!activeCard) return null;
  const fromStage = getCardStage(activeCard);

  // `over.id` is either a stage id (dropped on an empty/underfilled column's
  // droppable zone) or another card's id (dropped over a sibling card).
  const overIsColumn = columns.some((c) => c.stage.id === overId);

  let toStage: TStageId;
  let toIndex: number;

  if (overIsColumn) {
    toStage = overId as TStageId;
    const destColumn = columns.find((c) => c.stage.id === toStage);
    toIndex = destColumn ? destColumn.cards.length : 0;
  } else {
    const overCard = allCards.find((c) => getCardId(c) === overId);
    if (!overCard) return null;
    toStage = getCardStage(overCard);
    const destColumn = columns.find((c) => c.stage.id === toStage);
    const idx = destColumn ? destColumn.cards.findIndex((c) => getCardId(c) === overId) : -1;
    toIndex = idx >= 0 ? idx : destColumn ? destColumn.cards.length : 0;
  }

  // No-op guard: dropped back into the exact same slot it started in.
  if (fromStage === toStage) {
    const fromColumn = columns.find((c) => c.stage.id === fromStage);
    const currentIndex = fromColumn ? fromColumn.cards.findIndex((c) => getCardId(c) === activeCardId) : -1;
    if (currentIndex === toIndex) return null;
  }

  return { fromStage, toStage, toIndex };
}
