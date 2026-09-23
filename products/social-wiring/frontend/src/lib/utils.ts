/**
 * Shared utility functions for Social Wiring frontend.
 *
 * Re-exports the canonical helpers from `@noctusai/lib/utils` so product
 * code imports `cn`, `formatCurrency`, `formatDate`, `getTodayAtMidnight`,
 * `stripTime` from `@/lib/utils` (one local import) instead of crossing
 * the seed boundary in every component. Mirrors the 5-product convention
 * (core, dev-team, ERP, PF, therapy) and the live-validated CMS source.
 *
 * Add product-specific helpers below the re-export (e.g., a `slugify`
 * for the video URL scheme). Don't redefine helpers that already live
 * in the lib — if you find yourself copying one, lift it to
 * `@noctusai/lib/utils` instead (recurrence rule).
 */
export { cn, formatCurrency, formatDate, getTodayAtMidnight, stripTime } from "@noctusai/lib/utils";

/**
 * Bug 4 (prod card 755253934) — "Novo contato" showed 22/09/2026 21:00 for a
 * lead whose `data_entrada` (a DATE column, no time-of-day) is 2026-09-23.
 * `data_entrada` reaches the timeline's `touch` entry as `ocorrido_em`
 * serialized as a full ISO timestamp AT MIDNIGHT UTC (`…T00:00:00Z` /
 * `…T00:00:00+00:00`) rather than a bare `YYYY-MM-DD` — the seed's own
 * `formatDate` (`@noctusai/lib/utils`) already renders a BARE date-only
 * string without a TZ shift (`new Date(year, month-1, day)`, a LOCAL
 * constructor), but its date-only regex is `^\d{4}-\d{2}-\d{2}$` and does
 * not match this shape, so it falls through to `new Date(isoString)` —
 * which, WITH an explicit UTC offset, parses as UTC midnight and renders
 * 3h (America/Sao_Paulo) into the PREVIOUS calendar day.
 *
 * Deliberately narrow: only a timestamp EXACTLY at UTC midnight (down to the
 * second, with a `Z`/`+00:00` offset) is treated as a mis-serialized date —
 * a genuine event that happens to fire at 21:00 local time (midnight UTC)
 * is vanishingly unlikely for a human-driven CRM activity, and this is only
 * applied to the ONE kind (`touch`) known to trace back to a DATE column
 * (`Timeline.tsx`'s `SW_TIMELINE_RENDERERS` docblock — "the one kind only
 * SW's backend gathers"), never blindly to every timeline entry.
 */
const UTC_MIDNIGHT_RE = /^(\d{4}-\d{2}-\d{2})T00:00:00(?:\.0+)?(?:Z|\+00:00)$/;

export function dataOnlyFromPossibleUtcMidnight(value: string): string {
  const match = UTC_MIDNIGHT_RE.exec(value);
  return match ? match[1] : value;
}
