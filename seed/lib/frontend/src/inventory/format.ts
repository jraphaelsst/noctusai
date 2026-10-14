/** Inventory display helpers. Quantities keep up to 3 decimals (KG); money reuses the commerce cents seam. */
import { formatCents } from '../organ-kit/money';

export { formatCents };

/** `2.5` -> `2,5`; `1234` -> `1.234`; never more than 3 decimals, no trailing zeros. */
export function formatQty(value: number | string | null | undefined, locale = 'pt-BR'): string {
  const n = typeof value === 'string' ? Number(value) : (value ?? 0);
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 3, minimumFractionDigits: 0 }).format(Number.isFinite(n) ? n : 0);
}

/**
 * User-typed quantity -> canonical decimal string for the wire (`'2,5'` -> `'2.5'`), or `null` when it is not a
 * non-negative number with at most 3 decimals. Thousands dots are accepted only in the `1.234,5` form.
 */
export function parseQty(input: string): string | null {
  const raw = input.trim().replace(/\s/g, '');
  if (!raw || !/^[0-9.,]+$/.test(raw)) return null;
  let normalized: string;
  if (raw.includes(',')) normalized = raw.replace(/\./g, '').replace(',', '.');
  else if (/^[0-9]{1,3}(\.[0-9]{3}){2,}$/.test(raw)) normalized = raw.replace(/\./g, '');
  else normalized = raw;
  if (!/^[0-9]+(\.[0-9]{1,3})?$/.test(normalized)) return null;
  return normalized;
}

export function formatDateTime(iso: string | null | undefined, locale = 'pt-BR'): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString(locale, { dateStyle: 'short', timeStyle: 'short' });
}

/** Default item label when the host does not supply names: the first 8 chars of the id. */
export function shortId(id: string): string {
  return id.slice(0, 8);
}
