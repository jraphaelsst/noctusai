/**
 * Shared utility functions for Agentes frontend.
 *
 * Re-exports the canonical helpers from `@noctusai/lib/utils` so product
 * code imports `cn`, `formatDate`, `getTodayAtMidnight`, `stripTime`
 * from `@/lib/utils` (one local import) instead of crossing the seed
 * boundary in every component. Mirrors the 5-product convention
 * (core, dev-team, ERP, PF, therapy).
 *
 * TODO(new-product): add product-specific helpers below the re-export
 * (e.g., a domain-flavored `formatCurrency`, a `slugify` for your
 * URL scheme). Don't redefine helpers that already live in the lib —
 * if you find yourself copying one, lift it to `@noctusai/lib/utils`
 * instead (recurrence rule).
 */
export { cn, formatDate, getTodayAtMidnight, stripTime } from "@noctusai/lib/utils";

/**
 * `custo_usd`/`limite_usd` display (Agent Studio CONTRACT.md §L "Controle de
 * custo"). Deliberately NOT `@noctusai/lib/utils`'s `formatCurrency` — that
 * one is BRL-locked (`Intl.NumberFormat('pt-BR', {currency: 'BRL'})`); every
 * §L figure is a USD Anthropic-credit amount, so a distinct helper avoids a
 * silent currency-label lie. 2-4 decimals: the SMALLEST precision in that
 * range that round-trips the value exactly — a round figure ($2, $0.01)
 * stays at the familiar 2dp, while a sub-cent per-case cost (generator+judge
 * on a cheap case can land well under $0.01) grows to 3 or 4dp rather than
 * rounding to "$0.00", which would read as free. `null` (no `ResultMessage`
 * observed / result not yet costed) renders "—", NEVER "$0.00" — collapsing
 * "unknown" into "free" is exactly the invisible-cost failure this slice
 * exists to fix (CONTRACT.md §L WHY).
 */
export function formatUsdCost(value: number | null | undefined): string {
  if (value == null) return "—";
  for (const decimals of [2, 3, 4]) {
    const rounded = Number(value.toFixed(decimals));
    if (decimals === 4 || Math.abs(rounded - value) < 1e-9) {
      return `US$${value.toFixed(decimals)}`;
    }
  }
  /* istanbul ignore next -- unreachable: the loop above always returns by decimals===4 */
  return `US$${value.toFixed(4)}`;
}
