/**
 * Money for the organs. Money is integer CENTS everywhere; floats never cross the wire.
 * `formatCents` is the single display seam; `parseMoneyToCents` / `centsToInput` are the typed-input pair.
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
