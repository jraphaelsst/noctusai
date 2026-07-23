/**
 * formatCurrency — money formatter for the Meta Ads console.
 *
 * The whole ads pipeline carries money as INTEGER CENTS (the DB columns
 * and the `/api/meta/ads/*` DTOs are all `*_cents`). This is the single
 * place cents → a localized currency string, so a display never
 * double-divides. Currency comes from the ad account (`/accounts` →
 * `currency`, e.g. "BRL"); default pt-BR / BRL for the pilot account.
 */

/** Integer cents → localized currency string. `null`/`undefined` → "—". */
export function formatCents(
  cents: number | null | undefined,
  currency = "BRL",
  locale = "pt-BR",
): string {
  if (cents === null || cents === undefined) return "—";
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency,
  }).format(cents / 100);
}

/**
 * Δ% formatter for period-comparison tiles. Returns a signed pct string
 * plus a direction, or null when the delta is undefined (e.g. prior
 * window had no data). `pct` arrives already as a percentage number from
 * the backend `deltas` map (e.g. 12.5 → "+12,5%").
 */
export function formatDelta(
  pct: number | null | undefined,
): { label: string; dir: "up" | "down" | "flat" } | null {
  if (pct === null || pct === undefined || Number.isNaN(pct)) return null;
  const dir = pct > 0 ? "up" : pct < 0 ? "down" : "flat";
  const sign = pct > 0 ? "+" : "";
  const label = `${sign}${pct.toLocaleString("pt-BR", {
    maximumFractionDigits: 1,
  })}%`;
  return { label, dir };
}
