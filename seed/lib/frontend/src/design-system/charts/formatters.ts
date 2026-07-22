/**
 * Value formatters shared by the chart/KPI organs. Pure, DOM-free — see
 * `palette.ts` header for why pure logic is split out from render components.
 *
 * `formatCompactNumber` mirrors (and is the seed-canonical replacement
 * candidate for — see the return-note scoped-improvement) the pt-BR K/M
 * formatter already duplicated in `products/social-wiring/frontend/src/lib/formatNumber.ts`.
 * Migrating that existing consumer is out of this slice's scope (pilot-products-first
 * cadence); it is logged, not silently left to recur a 3rd time.
 */

/** `1234` -> "1,2 mil" style compact pt-BR number, K/M suffixed like the existing product helper. */
export function formatCompactNumber(value: number | null | undefined): string {
  const v = value ?? 0;
  if (!Number.isFinite(v)) return "—";
  const abs = Math.abs(v);
  if (abs >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
  return v.toLocaleString("pt-BR");
}

/**
 * Percent delta formatter. `value` is ALREADY in percent units (`23.4`, not
 * `0.234` — matches the Leads API contract's `variacao_pct`/`share_pct`).
 * Signed (`+23.4%` / `-5.0%`); `0` renders as `0.0%` (a real, resolved zero —
 * NOT the same case as `null`, which the caller must render as "—" upstream
 * of this formatter, see `StatTile`).
 */
export function formatPercentDelta(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}%`;
}

/** Plain 1-decimal percent, unsigned (`share_pct` rendering — "23,4%"). */
export function formatPercent(value: number): string {
  return `${value.toFixed(1).replace(".", ",")}%`;
}

/** pt-BR short month labels, index 0 = Janeiro — matches `mes-1` array indexing in the Leads heatmap. */
export const PT_BR_MONTH_LABELS_SHORT = [
  "Jan",
  "Fev",
  "Mar",
  "Abr",
  "Mai",
  "Jun",
  "Jul",
  "Ago",
  "Set",
  "Out",
  "Nov",
  "Dez",
] as const;
