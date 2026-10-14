/**
 * Quote display helpers. Money is integer cents and reuses the organ-kit seam; quantities reuse the inventory
 * organ's (`formatQty` / `parseQty`, up to 3 decimals). `previewTotals` mirrors the server's HALF-UP per-line
 * rounding so the editor's live numbers match what the server stores — the server stays the validator of record.
 */
import { centsToInput, formatCents, parseMoneyToCents } from '../organ-kit/money';
import { formatQty, parseQty } from '../inventory/format';

export { centsToInput, formatCents, formatQty, parseMoneyToCents, parseQty };

/** `2026-10-14` -> `14/10/2026` (no timezone shift: a date-only value is not an instant). */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : '—';
}

export function formatDateTime(iso: string | null | undefined, locale = 'pt-BR'): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString(locale, { dateStyle: 'short', timeStyle: 'short' });
}

/** Round-half-up of `qty × unitPriceCents` on exact decimals (the qty has at most 3 places: scale to integers). */
export function lineGrossCents(qty: string, unitPriceCents: number): number | null {
  const q = parseQty(qty);
  if (q === null || !Number.isInteger(unitPriceCents) || unitPriceCents < 0) return null;
  const [whole, frac = ''] = q.split('.');
  const scaled = BigInt(whole + frac.padEnd(3, '0')) * BigInt(unitPriceCents); // value × 1000
  return Number((scaled + 500n) / 1000n);
}

export interface PreviewLine {
  qty: string;
  unitPriceCents: number;
  discountCents: number;
}
export interface PreviewTotals {
  lineTotals: Array<number | null>;
  subtotal: number;
  discount: number;
  total: number;
  /** A line or the header discount is over its base — the editor shows it, the server refuses it. */
  invalid: boolean;
}

export function previewTotals(lines: PreviewLine[], discountCents: number): PreviewTotals {
  let invalid = false;
  const lineTotals = lines.map((l) => {
    const gross = lineGrossCents(l.qty, l.unitPriceCents);
    if (gross === null || l.discountCents < 0 || l.discountCents > gross) {
      invalid = true;
      return null;
    }
    return gross - l.discountCents;
  });
  const subtotal = lineTotals.reduce<number>((a, b) => a + (b ?? 0), 0);
  if (discountCents < 0 || discountCents > subtotal) invalid = true;
  return { lineTotals, subtotal, discount: discountCents, total: subtotal - discountCents, invalid };
}
