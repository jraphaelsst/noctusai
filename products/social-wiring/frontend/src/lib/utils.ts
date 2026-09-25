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

/**
 * Strips CPF/CNPJ mask separators — the CLEANED value is what a form
 * submits; the backend normalises/validates it further (check digits,
 * 400 not 422). Lifted from `NegociacaoEstruturadaPanel.tsx` (P1/883,
 * 2026-09-25, recurrence rule N=2) — `TestemunhasSection.tsx` needed the
 * SAME CPF display formatting and this was the only one anywhere in
 * `seed/lib/frontend`/this product, just not shared yet.
 */
export function limparDocumento(v: string): string {
  return v.replace(/[.\-/\s]/g, "").toUpperCase();
}

/**
 * Progressive CPF/CNPJ mask — position-based, not digit-only, since a CNPJ
 * may be alphanumeric (since July 2026). Doubles as a DISPLAY formatter
 * for an already-complete document (11 or 14 chars in): fed a full raw
 * CPF it renders the standard `999.999.999-99` grouping in one pass, the
 * same as it does progressively while a form field is still being typed.
 */
export function formatarDocumento(bruto: string): string {
  const s = limparDocumento(bruto).slice(0, 14);
  if (s.length <= 11) {
    const partes = [s.slice(0, 3), s.slice(3, 6), s.slice(6, 9), s.slice(9, 11)].filter(
      Boolean,
    );
    let out = partes[0] ?? "";
    if (partes[1]) out += `.${partes[1]}`;
    if (partes[2]) out += `.${partes[2]}`;
    if (partes[3]) out += `-${partes[3]}`;
    return out;
  }
  const partes = [s.slice(0, 2), s.slice(2, 5), s.slice(5, 8), s.slice(8, 12), s.slice(12, 14)];
  let out = partes[0] ?? "";
  if (partes[1]) out += `.${partes[1]}`;
  if (partes[2]) out += `.${partes[2]}`;
  if (partes[3]) out += `/${partes[3]}`;
  if (partes[4]) out += `-${partes[4]}`;
  return out;
}
