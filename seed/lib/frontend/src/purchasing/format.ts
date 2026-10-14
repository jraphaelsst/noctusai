/** Purchasing display helpers. Quantities/money parsing reuse the inventory + commerce seams (one answer per rule). */
import { formatCents, parseMoneyToCents } from '../commerce/format';
import { formatQty, parseQty } from '../inventory/format';

export { formatCents, formatQty, parseMoneyToCents, parseQty };

/** A line total exactly as the server computes it: `round(qty × unit_cost)`, half away from zero (costs are ≥ 0). */
export function lineTotalCents(qty: string | number, unitCostCents: number): number {
  const q = typeof qty === 'string' ? Number(qty) : qty;
  return Number.isFinite(q) ? Math.round(q * unitCostCents) : 0;
}

/** `2026-10-14` -> `14/10/2026` (no timezone shift: the value is a calendar date). */
export function formatDate(value: string | null | undefined): string {
  if (!value) return '—';
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : '—';
}

export function shortId(id: string): string {
  return id.slice(0, 8);
}

/** A fresh idempotency key for one receive attempt (kept for the dialog's lifetime so a retry is a replay). */
export function newIdempotencyKey(): string {
  const c = (globalThis as { crypto?: { randomUUID?: () => string } }).crypto;
  return c?.randomUUID ? c.randomUUID() : `rk-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

/** Decimal string of `n` with at most 3 places and no trailing zeros (`10` -> `'10'`, `2.5` -> `'2.5'`). */
export function qtyToWire(n: number): string {
  return String(Number(n.toFixed(3)));
}
