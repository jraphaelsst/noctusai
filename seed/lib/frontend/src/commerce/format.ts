/**
 * Commerce money + small helpers. Money is integer CENTS everywhere; floats
 * never cross the wire. `formatCents` is the single display seam.
 */

/** Integer cents → localized currency string (`123456` → `R$ 1.234,56`). */
export function formatCents(cents: number | null | undefined, currency = 'BRL', locale = 'pt-BR'): string {
  const value = (cents ?? 0) / 100;
  return new Intl.NumberFormat(locale, { style: 'currency', currency }).format(value);
}

/**
 * User-typed BRL amount → integer cents, or `null` if it is not a valid
 * non-negative amount. Accepts `12`, `12,5`, `12,50`, `1.234,56`, `12.50`,
 * `R$ 12,50`. A lone `.` followed by exactly 3 digits is a thousands
 * separator (`1.234` = 1234,00); otherwise `.` is a decimal point.
 */
export function parseMoneyToCents(input: string): number | null {
  const raw = input.replace(/R\$|\s/g, '');
  if (!raw || !/^[0-9.,]+$/.test(raw)) return null;
  let normalized: string;
  if (raw.includes(',')) {
    normalized = raw.replace(/\./g, '').replace(',', '.');
  } else if (/^[0-9]{1,3}(\.[0-9]{3})+$/.test(raw)) {
    normalized = raw.replace(/\./g, '');
  } else {
    normalized = raw;
  }
  if (!/^[0-9]+(\.[0-9]{1,2})?$/.test(normalized)) return null;
  const [whole, frac = ''] = normalized.split('.');
  return Number(whole) * 100 + Number(frac.padEnd(2, '0'));
}

/** Integer cents → editable input string (`1250` → `12,50`). */
export function centsToInput(cents: number | null | undefined): string {
  if (cents == null) return '';
  const whole = Math.trunc(cents / 100);
  const frac = String(Math.abs(cents % 100)).padStart(2, '0');
  return `${whole},${frac}`;
}

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
