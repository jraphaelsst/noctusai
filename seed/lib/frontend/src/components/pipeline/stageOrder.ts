/**
 * `mergeVisibleStageOrder` — turn a reorder of the BOARD's columns into the
 * FULL stage order the API needs.
 *
 * The board renders only ACTIVE stages, but `POST <stages>/reordenar` demands
 * every stage of the pipeline, inactive included (`reorder_stages` in the seed
 * backend refuses a partial order — a partial reorder forces the server to
 * guess where everything else went). Sending only the visible ids would 400
 * on any pipeline that has ever retired a stage.
 *
 * So: take the full list in its current order, and refill ONLY the slots the
 * visible stages occupy, in their new order. Hidden stages keep their exact
 * slots; nothing the user could not see moves.
 */
export interface OrderableStage {
  id: string;
  posicao: number;
  slug?: string;
}

export function mergeVisibleStageOrder(
  allStages: readonly OrderableStage[],
  visibleOrder: readonly string[],
): string[] {
  if (allStages.length === 0) return [...visibleOrder];

  // Same ordering the backend uses: posicao, then slug as the stable tiebreak.
  const ordered = [...allStages].sort(
    (a, b) => a.posicao - b.posicao || (a.slug ?? '').localeCompare(b.slug ?? ''),
  );
  const known = new Set(ordered.map((s) => s.id));
  // A visible id the stage list does not know means the two queries are out
  // of step (a stage created a moment ago). Send what the board shows and let
  // the server's validation answer — never invent positions for it.
  if (visibleOrder.some((id) => !known.has(id))) return [...visibleOrder];

  const visible = new Set(visibleOrder);
  const queue = [...visibleOrder];
  return ordered.map((s) => (visible.has(s.id) ? (queue.shift() as string) : s.id));
}
