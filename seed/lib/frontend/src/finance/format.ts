/**
 * Finance formatting helpers. Money is integer CENTS; `formatCents` / `parseMoneyToCents` /
 * `centsToInput` are the commerce organ's (one display seam for the whole platform) and are
 * re-exported here rather than duplicated.
 */
export { formatCents, parseMoneyToCents, centsToInput, formatDateTime } from '../commerce/format';

const MONTHS_PT = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];

/** `2026-10-14` → `14/10/2026` (string slicing: no timezone shift on a date-only value). */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : iso;
}

/** `2026-10` or `2026-10-01` → `out/2026`. */
export function formatMonth(key: string | null | undefined): string {
  if (!key) return '—';
  const m = /^(\d{4})-(\d{2})/.exec(key);
  if (!m) return key;
  return `${MONTHS_PT[Number(m[2]) - 1] ?? m[2]}/${m[1]}`;
}

/** Local calendar day as `YYYY-MM-DD`. */
export function toIsoDate(d: Date): string {
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${mm}-${dd}`;
}
export function todayIso(now: Date = new Date()): string {
  return toIsoDate(now);
}
/** First day of `now`'s month, shifted by `monthsAhead` months. */
export function monthStartIso(now: Date = new Date(), monthsAhead = 0): string {
  return toIsoDate(new Date(now.getFullYear(), now.getMonth() + monthsAhead, 1));
}
/** Last day of `now`'s month shifted by `monthsAhead`. */
export function monthEndIso(now: Date = new Date(), monthsAhead = 0): string {
  return toIsoDate(new Date(now.getFullYear(), now.getMonth() + monthsAhead + 1, 0));
}
/** `2026-10-14` → `2026-10-01` (competence month is always the 1st). */
export function toCompetenceMonth(isoDay: string): string {
  return `${isoDay.slice(0, 7)}-01`;
}

/** What is still open on an entry (never negative). */
export function remainingCents(e: { amount_cents: number; settled_cents: number }): number {
  return Math.max(0, e.amount_cents - e.settled_cents);
}

/** `{a: 1, b: ''}` → `?a=1` (drops empty values). */
export function buildQuery(params: Record<string, unknown> = {}): string {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '') continue;
    qs.set(k, String(v));
  }
  const s = qs.toString();
  return s ? `?${s}` : '';
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1).replace('.', ',')} KB`;
  return `${(n / 1024 / 1024).toFixed(1).replace('.', ',')} MB`;
}
