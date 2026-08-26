/**
 * useDebouncedValue — `value`, but only after it has stopped changing.
 *
 * For a live-fetch typeahead: without it, "ONE9481" is seven keystrokes and
 * seven round trips, and the answers can land out of order.
 *
 * N=2 TRIAGE (DRY, the recurrence rule)
 * -------------------------------------
 * `pages/leads/components/LeadsFilterBar.tsx` already debounces, inline, with
 * its own `setTimeout` + ref + cleanup. This is the second instance, so the
 * rule says triage rather than formalize — and the verdict is: extract the
 * hook (here), do NOT retrofit `LeadsFilterBar` in this branch. That file is
 * outside this slice and another agent is working the leads surface; a
 * drive-by refactor there buys nothing and risks a collision.
 *
 * A THIRD debounce is where the retrofit becomes mandatory. It should consume
 * this hook rather than add another inline timer.
 */
import { useEffect, useState } from "react";

export function useDebouncedValue<T>(value: T, delayMs = 250): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    // Cleanup is what makes it a debounce rather than a delay: without it,
    // every keystroke schedules its own fire and they all land.
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}
