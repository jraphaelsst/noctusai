/**
 * Formatting for the turn-metrics page (pt-BR). A missing value is "—", never 0 (canon §8).
 * Money here is USD straight from the priced ledger events (never converted to BRL).
 */
const usd = (digits: number) =>
  new Intl.NumberFormat("pt-BR", { style: "currency", currency: "USD", minimumFractionDigits: digits, maximumFractionDigits: digits });
const USD_2 = usd(2);
const USD_4 = usd(4);
const INT = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
const DEC1 = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

const ok = (v: number | null | undefined): v is number => v != null && Number.isFinite(v);

/** Total cost (2 decimals) or per-turn cost (4 decimals). */
export function fmtUsd(v: number | null | undefined, digits: 2 | 4 = 2): string {
  return ok(v) ? (digits === 4 ? USD_4 : USD_2).format(v) : "—";
}

export function fmtInt(v: number | null | undefined): string {
  return ok(v) ? INT.format(v) : "—";
}

/** `0.97` -> "97,0%". */
export function fmtShare(v: number | null | undefined): string {
  return ok(v) ? `${DEC1.format(v * 100)}%` : "—";
}

/** Milliseconds -> "850 ms" under 1 s, otherwise "1,7 s". */
export function fmtMs(v: number | null | undefined): string {
  if (!ok(v)) return "—";
  return v < 1000 ? `${INT.format(v)} ms` : `${DEC1.format(v / 1000)} s`;
}

/** UTF-8 payload bytes -> "64 B" / "1,2 KB" / "3,4 MB". */
export function fmtBytes(v: number | null | undefined): string {
  if (!ok(v)) return "—";
  if (v < 1024) return `${INT.format(v)} B`;
  if (v < 1024 * 1024) return `${DEC1.format(v / 1024)} KB`;
  return `${DEC1.format(v / (1024 * 1024))} MB`;
}

/** Average of a total over `n` turns (null when there are no turns — not 0). */
export function media(total: number, n: number): number | null {
  return n > 0 ? total / n : null;
}
