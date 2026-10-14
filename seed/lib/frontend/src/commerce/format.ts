/**
 * Commerce money + small helpers. Money is integer CENTS everywhere; floats
 * never cross the wire. `formatCents` is the single display seam.
 */

// Money lives in the shared organ kit; re-exported so existing `commerce/format` importers keep working.
export { formatCents, parseMoneyToCents, centsToInput } from '../organ-kit/money';

export function onlyDigits(s: string): string {
  return s.replace(/\D/g, '');
}

/** Progressive CNPJ mask `00.000.000/0000-00` (digits only; alphanumeric CNPJ is out of scope for the input mask). */
export function maskCnpj(value: string): string {
  const d = onlyDigits(value).slice(0, 14);
  let out = d.slice(0, 2);
  if (d.length > 2) out += '.' + d.slice(2, 5);
  if (d.length > 5) out += '.' + d.slice(5, 8);
  if (d.length > 8) out += '/' + d.slice(8, 12);
  if (d.length > 12) out += '-' + d.slice(12, 14);
  return out;
}

/** Progressive CPF mask `000.000.000-00`. */
export function maskCpf(value: string): string {
  const d = onlyDigits(value).slice(0, 11);
  let out = d.slice(0, 3);
  if (d.length > 3) out += '.' + d.slice(3, 6);
  if (d.length > 6) out += '.' + d.slice(6, 9);
  if (d.length > 9) out += '-' + d.slice(9, 11);
  return out;
}

/** Mask as CPF while ≤11 digits, CNPJ above. */
export function maskCpfOrCnpj(value: string): string {
  return onlyDigits(value).length > 11 ? maskCnpj(value) : maskCpf(value);
}

export function slugify(s: string): string {
  return s
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

export function formatDateTime(iso: string | null | undefined, locale = 'pt-BR'): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(locale, { dateStyle: 'short', timeStyle: 'short' });
}
