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

/**
 * Prefix for a COLUMN's sortable id when columns are drag-reorderable.
 *
 * A column already owns one droppable whose id IS the stage id (the drop zone
 * for cards). Its sortable wrapper needs a second, distinct id — reusing the
 * stage id would register two droppables under one key and dnd-kit would keep
 * only one of them. The prefix also lets every consumer of a drag event tell
 * "a column moved" from "a card moved" by id alone, even without `data.type`.
 */
export const KANBAN_COLUMN_DND_PREFIX = 'kanban-column:';

/** The sortable id a column registers under when columns are reorderable. */
export function columnDndId(stageId: string): string {
  return `${KANBAN_COLUMN_DND_PREFIX}${stageId}`;
}

/** Stage id carried by a column sortable id, or `null` for anything else. */
export function stageIdFromColumnDndId(id: string): string | null {
  return id.startsWith(KANBAN_COLUMN_DND_PREFIX)
    ? id.slice(KANBAN_COLUMN_DND_PREFIX.length)
    : null;
}

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
  // A COLUMN drag is never a card move. The board routes column drags to
  // `computeColumnReorder`, but this guard keeps the function honest on its
  // own: a stray column id must resolve to "nothing moved", never to a card.
  if (stageIdFromColumnDndId(activeCardId) !== null) return null;

  // A card dropped on a column's SORTABLE wrapper (the header area, when
  // columns are reorderable) means "into that column" — same as its drop zone.
  const target = stageIdFromColumnDndId(overId) ?? overId;

  const allCards = columns.flatMap((c) => c.cards);
  const activeCard = allCards.find((c) => getCardId(c) === activeCardId);
  if (!activeCard) return null;
  const fromStage = getCardStage(activeCard);

  // `over.id` is either a stage id (dropped on an empty/underfilled column's
  // droppable zone) or another card's id (dropped over a sibling card).
  const overIsColumn = columns.some((c) => c.stage.id === target);

  let toStage: TStageId;
  let toIndex: number;

  if (overIsColumn) {
    toStage = target as TStageId;
    const destColumn = columns.find((c) => c.stage.id === toStage);
    toIndex = destColumn ? destColumn.cards.length : 0;
  } else {
    const overCard = allCards.find((c) => getCardId(c) === target);
    if (!overCard) return null;
    toStage = getCardStage(overCard);
    const destColumn = columns.find((c) => c.stage.id === toStage);
    const idx = destColumn ? destColumn.cards.findIndex((c) => getCardId(c) === target) : -1;
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

/**
 * Resolve a COLUMN drag into the new full column order, or `null` when nothing
 * moved. Accepts either raw stage ids or column sortable ids for both ends, so
 * the caller can pass dnd-kit's `active.id` / `over.id` straight through.
 *
 * Returns the FULL order (not a `(id, index)` pair) because that is what the
 * stage API's `/reordenar` takes — see `reorder_stages` in the seed backend.
 */
export function computeColumnReorder<TStageId extends string = string>(
  stageIds: readonly TStageId[],
  activeId: string,
  overId: string,
): TStageId[] | null {
  const from = stageIds.indexOf((stageIdFromColumnDndId(activeId) ?? activeId) as TStageId);
  const to = stageIds.indexOf((stageIdFromColumnDndId(overId) ?? overId) as TStageId);
  if (from < 0 || to < 0 || from === to) return null;
  const next = [...stageIds];
  const [moved] = next.splice(from, 1);
  next.splice(to, 0, moved);
  return next;
}
