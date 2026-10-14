import { formatCents } from '../organ-kit/money';

/** ISO date `2026-11-10` -> `10/11/2026` (no timezone shift: the string is cut, never parsed as an instant). */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const [y, m, d] = iso.slice(0, 10).split('-');
  return y && m && d ? `${d}/${m}/${y}` : iso;
}

/** Basis points -> `4,50`. */
export function bpToPercent(bp: number | null | undefined): string {
  return ((bp ?? 0) / 100).toFixed(2).replace('.', ',');
}

/** User-typed percentage (`4,5`, `4.50`) -> basis points, or null if invalid / negative / above 1000%. */
export function percentToBp(input: string): number | null {
  const raw = input.trim().replace('%', '').replace(',', '.');
  if (!/^[0-9]+(\.[0-9]{1,2})?$/.test(raw)) return null;
  const bp = Math.round(Number(raw) * 100);
  return bp <= 100000 ? bp : null;
}

/** Minutes <-> hours for the retainer franchise (`600` <-> `10`). */
export const minutesToHours = (m: number | null | undefined): string => (m == null ? '' : String(+(m / 60).toFixed(2)).replace('.', ','));
export function hoursToMinutes(input: string): number | null {
  const raw = input.trim().replace(',', '.');
  if (!/^[0-9]+(\.[0-9]{1,2})?$/.test(raw)) return null;
  return Math.round(Number(raw) * 60);
}

/** The value a contract row shows: per-period for open-ended models, total otherwise. */
export function amountLabel(model: string, cents: number): string {
  return model === 'recurring' || model === 'retainer' ? `${formatCents(cents)}/${model === 'retainer' ? 'mês' : 'período'}` : formatCents(cents);
}

export function linesTotal(lines: { quantity: number; unit_price_cents: number }[]): number {
  return lines.reduce((sum, l) => sum + l.quantity * l.unit_price_cents, 0);
}
