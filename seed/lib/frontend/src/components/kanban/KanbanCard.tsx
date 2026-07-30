/**
 * `<KanbanCard/>` — the drag-wiring wrapper. Card *content* is always the
 * consumer's own component (passed as `children`); this wrapper only owns
 * the `@dnd-kit/sortable` plumbing (ref, transform style, a11y attributes,
 * pointer + keyboard listeners) so the consumer's card component never
 * needs to import `@dnd-kit/*` itself.
 *
 * CLICK-TO-OPEN LIVES HERE, NOT IN THE CARD CONTENT
 * -------------------------------------------------
 * A card that opens a detail view on click is competing with the drag
 * listeners on the same element. The board's PointerSensor only starts a
 * drag after 8px of movement, so a still-pointer click never becomes a
 * drag — but the reverse is NOT free: releasing a drag fires a trailing
 * `click` on the element, so a naive `onClick` opens a modal every time
 * the user moves a card between columns.
 *
 * The fix is a pointer-distance guard, and it belongs on this wrapper for
 * the same reason the drag listeners do: it is drag plumbing, and every
 * board that wants clickable cards would otherwise re-derive it (wrongly,
 * in slightly different ways) inside its own card component.
 */
import * as React from 'react';
import type { ReactNode } from 'react';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

/**
 * Must match the board's `PointerSensor` activation distance. Below it the
 * gesture was never a drag, so it was a click.
 */
const CLICK_SLOP_PX = 8;

export interface KanbanCardProps {
  /** The card's stable id — must match `getCardId(card)` in the board. */
  id: string;
  children: ReactNode;
  className?: string;
  /**
   * Fired for a genuine click — a pointer press and release within
   * `CLICK_SLOP_PX`. A drag never triggers it, and neither does the
   * trailing click a drag release emits.
   *
   * Interactive elements INSIDE the card (buttons, links) should still call
   * `stopPropagation` in their own handlers: this fires on the card, and a
   * button click is not a card click.
   */
  onActivate?: () => void;
}

export function KanbanCard({ id, children, className, onActivate }: KanbanCardProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id,
  });

  const pressOrigin = React.useRef<{ x: number; y: number } | null>(null);

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  // `listeners` carries dnd-kit's own onPointerDown; compose rather than
  // replace, or the card stops being draggable.
  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    // Record the origin ONLY when it is usable. An event without real
    // coordinates (a synthetic dispatch, an environment with no
    // PointerEvent) must not become an origin — `Math.hypot` of a NaN is
    // NaN, every comparison against it is false, and the guard would
    // silently degrade to "every gesture is a click" with nothing to show
    // for it.
    pressOrigin.current =
      Number.isFinite(e.clientX) && Number.isFinite(e.clientY)
        ? { x: e.clientX, y: e.clientY }
        : null;
    listeners?.onPointerDown?.(e);
  };

  const handleClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!onActivate) return;
    const origin = pressOrigin.current;
    // Consume it either way: a stale origin would be measured against the
    // NEXT click, judging one gesture by another's starting point.
    pressOrigin.current = null;

    // No usable origin — a keyboard-driven or programmatic click, or an
    // assistive technology dispatching one. Only an actual, measurable
    // pointer journey can disqualify a click.
    if (origin && Number.isFinite(e.clientX) && Number.isFinite(e.clientY)) {
      const moved = Math.hypot(e.clientX - origin.x, e.clientY - origin.y);
      if (moved >= CLICK_SLOP_PX) return;
    }
    onActivate();
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      onPointerDown={handlePointerDown}
      onClick={onActivate ? handleClick : undefined}
      // No onKeyDown here on purpose. dnd-kit's KeyboardSensor claims Enter
      // and Space through `listeners` to START a keyboard drag; binding our
      // own would silently replace it and make cards undraggable by keyboard.
      // Opening the detail view from the keyboard therefore needs a focusable
      // control INSIDE the card rather than a key handler on the card itself.
      className={className}
      data-kanban-card-id={id}
    >
      {children}
    </div>
  );
}
