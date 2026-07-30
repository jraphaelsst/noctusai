/**
 * The drag-vs-click guard on `KanbanCard`.
 *
 * This is the one piece of clickable-card behaviour that is easy to get
 * subtly wrong and impossible to notice in review: a naive `onClick` works
 * perfectly in every manual test EXCEPT the one where you drag a card, at
 * which point the modal opens on top of the move you just made.
 *
 * `@dnd-kit`'s sensors need real layout geometry that jsdom does not
 * compute (see `reference_lib_frontend_vitest_render_harness_gap`), so
 * these drive the pointer/click events directly rather than simulating a
 * full drag. That is the right level anyway — the claim under test is
 * "pointer travel ≥ the activation distance is not a click", and that is
 * exactly what these assert.
 */
/// <reference types="@testing-library/jest-dom" />
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { DndContext } from '@dnd-kit/core';
import { SortableContext } from '@dnd-kit/sortable';

import { KanbanCard } from './KanbanCard';

afterEach(cleanup);

function renderCard(onActivate?: () => void) {
  render(
    <DndContext>
      <SortableContext items={['c1']}>
        <KanbanCard id="c1" onActivate={onActivate}>
          <div>Ana</div>
        </KanbanCard>
      </SortableContext>
    </DndContext>,
  );
  return screen.getByText('Ana').parentElement as HTMLElement;
}

/**
 * jsdom implements no `PointerEvent`, so `fireEvent.pointerDown(el, {clientX})`
 * silently DROPS the coordinates — the handler receives `undefined`. Dispatching
 * a real `MouseEvent` typed `pointerdown` is what actually carries them, and
 * React's `onPointerDown` fires from it all the same.
 */
function pointerDownAt(el: HTMLElement, x: number, y: number) {
  fireEvent(
    el,
    new MouseEvent('pointerdown', { clientX: x, clientY: y, bubbles: true, cancelable: true }),
  );
}

/** A press and release at the same point — an unambiguous click. */
function clickAt(el: HTMLElement, x: number, y: number) {
  pointerDownAt(el, x, y);
  fireEvent.click(el, { clientX: x, clientY: y });
}

/** Press, travel, release — what finishing a drag looks like to the DOM. */
function dragFrom(el: HTMLElement, from: [number, number], to: [number, number]) {
  pointerDownAt(el, from[0], from[1]);
  fireEvent.click(el, { clientX: to[0], clientY: to[1] });
}

describe('onActivate — a click opens, a drag does not', () => {
  it('fires for a still-pointer click', () => {
    const onActivate = vi.fn();
    clickAt(renderCard(onActivate), 100, 100);
    expect(onActivate).toHaveBeenCalledTimes(1);
  });

  it('does NOT fire for the trailing click a completed drag emits', () => {
    // The regression this guard exists for: without it, every card moved
    // between columns also opens its detail modal.
    const onActivate = vi.fn();
    dragFrom(renderCard(onActivate), [100, 100], [260, 100]);
    expect(onActivate).not.toHaveBeenCalled();
  });

  it('tolerates the small jitter of a real finger or trackpad', () => {
    // Just under the 8px activation distance — the gesture never became a
    // drag, so it was a click, and demanding pixel-perfection would make
    // touch users unable to open a card at all.
    const onActivate = vi.fn();
    dragFrom(renderCard(onActivate), [100, 100], [104, 102]);
    expect(onActivate).toHaveBeenCalledTimes(1);
  });

  it('rejects travel exactly at the activation distance', () => {
    const onActivate = vi.fn();
    dragFrom(renderCard(onActivate), [100, 100], [108, 100]);
    expect(onActivate).not.toHaveBeenCalled();
  });

  it('measures diagonal travel, not just one axis', () => {
    // 6px right + 6px down is 8.49px of actual travel. Checking axes
    // independently would call this a click.
    const onActivate = vi.fn();
    dragFrom(renderCard(onActivate), [100, 100], [106, 106]);
    expect(onActivate).not.toHaveBeenCalled();
  });

  it('treats a click with no recorded press as a click', () => {
    // Programmatic / assistive-tech clicks arrive with no preceding
    // pointerdown. Only a real pointer journey can disqualify one.
    const onActivate = vi.fn();
    fireEvent.click(renderCard(onActivate));
    expect(onActivate).toHaveBeenCalledTimes(1);
  });

  it('treats a press with unusable coordinates as no press at all', () => {
    // An environment or synthetic dispatch that gives no clientX must not
    // become an origin: NaN arithmetic compares false against every
    // threshold, so the guard would quietly stop guarding.
    const onActivate = vi.fn();
    const el = renderCard(onActivate);
    fireEvent.pointerDown(el); // no coordinates
    fireEvent.click(el, { clientX: 900, clientY: 900 });
    expect(onActivate).toHaveBeenCalledTimes(1);
  });

  it('does not re-use a stale press for the next click', () => {
    // The press origin must be consumed, or a drag followed by a genuine
    // click on another card would be judged against the wrong origin.
    const onActivate = vi.fn();
    const el = renderCard(onActivate);
    dragFrom(el, [100, 100], [300, 100]);
    expect(onActivate).not.toHaveBeenCalled();
    fireEvent.click(el, { clientX: 300, clientY: 100 });
    expect(onActivate).toHaveBeenCalledTimes(1);
  });
});

describe('opt-in', () => {
  it('a card without onActivate is inert to clicks', () => {
    const el = renderCard(undefined);
    expect(() => clickAt(el, 10, 10)).not.toThrow();
  });

  it('stays draggable — dnd-kit attributes survive the added handlers', () => {
    const el = renderCard(() => {});
    expect(el).toHaveAttribute('data-kanban-card-id', 'c1');
    expect(el).toHaveAttribute('role', 'button');
  });
});
