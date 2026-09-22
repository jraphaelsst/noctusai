/**
 * The board's drag sensors — one place, so the card's click-slop guard and the
 * board's activation constraints can never disagree.
 *
 * WHY MOUSE + TOUCH, NOT ONE POINTER SENSOR
 * -----------------------------------------
 * A single `PointerSensor` with an 8px distance constraint treats a finger
 * exactly like a mouse: the first 8px of a vertical swipe START A DRAG. On a
 * phone that means the board steals the page scroll (or, when the browser wins
 * the race, fires `pointercancel` and the drag never works at all). Splitting
 * the input kinds lets each get the constraint it actually needs:
 *
 *  - Mouse: 8px distance — identical to the previous desktop behaviour, so a
 *    plain click on a button inside a card is never swallowed as a drag.
 *  - Touch: press-and-hold. A finger must stay (within `tolerance`) for
 *    `delay` ms before a drag starts; any earlier movement is a scroll and the
 *    activation is abandoned, so swiping across the board scrolls it natively.
 *  - Keyboard: unchanged — Tab to focus, Space to lift, arrows, Space to drop.
 *
 * The constraints are exported as data so tests can pin them without
 * simulating real pointer geometry (which jsdom cannot compute).
 */
import {
  KeyboardSensor,
  MouseSensor,
  TouchSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import { sortableKeyboardCoordinates } from '@dnd-kit/sortable';

/** Mouse drags start after this many px. `KanbanCard`'s click slop reads it too. */
export const KANBAN_MOUSE_DISTANCE_PX = 8;

/** Mouse activation: distance-based, so clicks inside cards stay clicks. */
export const KANBAN_MOUSE_ACTIVATION = { distance: KANBAN_MOUSE_DISTANCE_PX } as const;

/**
 * Touch activation: press-and-hold. 250ms is long enough that a scroll flick
 * never qualifies and short enough to feel immediate on a deliberate hold;
 * the tolerance absorbs natural finger jitter during the hold.
 */
export const KANBAN_TOUCH_ACTIVATION = { delay: 250, tolerance: 8 } as const;

/** The sensor set every kanban board (cards AND columns) drags with. */
export function useKanbanSensors() {
  return useSensors(
    useSensor(MouseSensor, { activationConstraint: KANBAN_MOUSE_ACTIVATION }),
    useSensor(TouchSensor, { activationConstraint: KANBAN_TOUCH_ACTIVATION }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
}
