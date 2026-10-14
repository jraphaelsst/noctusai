/**
 * Client-side mirrors of the backend fiscal validators (`domain/items/validators.py`).
 * FORMAT checks only, for instant feedback — the server is the authority and its 422 is always shown.
 * Sources and what is NOT verified: `seed/lib/backend/noctusai_lib/domain/items/ITEMS.md`.
 * Each `normalize*` returns the canonical stored form, `null` for blank, or `undefined` when invalid.
 */

const blank = (v: string | null | undefined): boolean => v == null || v.trim() === '';
const stripped = (v: string, separators: RegExp): string => v.trim().replace(separators, '').replace(/\s/g, '');

export function normalizeSku(v: string): string | undefined {
  const t = v.trim();
  return /^[A-Za-z0-9][A-Za-z0-9._/-]{0,63}$/.test(t) ? t.toUpperCase() : undefined;
}

export function normalizeNcm(v: string | null | undefined): string | null | undefined {
  if (blank(v)) return null;
  const d = stripped(v as string, /\./g);
  if (!/^\d{8}$/.test(d)) return undefined;
  const chapter = Number(d.slice(0, 2));
  return chapter >= 1 && chapter <= 97 ? d : undefined;
}

export function normalizeCest(v: string | null | undefined): string | null | undefined {
  if (blank(v)) return null;
  const d = stripped(v as string, /\./g);
  return /^\d{7}$/.test(d) ? d : undefined;
}

export function normalizeCfop(v: string | null | undefined): string | null | undefined {
  if (blank(v)) return null;
  const d = stripped(v as string, /\./g);
  return /^[123567]\d{3}$/.test(d) ? d : undefined;
}

/** GS1 mod-10 check digit of the digits BEFORE the check digit (weights 3,1,3,1… from the right). */
export function gtinCheckDigit(body: string): number {
  let total = 0;
  for (let i = 0; i < body.length; i += 1) {
    const digit = Number(body[body.length - 1 - i]);
    total += digit * (i % 2 === 0 ? 3 : 1);
  }
  return (10 - (total % 10)) % 10;
}

export function normalizeGtin(v: string | null | undefined): string | null | undefined {
  if (blank(v)) return null;
  const d = stripped(v as string, /-/g);
  if (!/^\d+$/.test(d) || ![8, 12, 13, 14].includes(d.length)) return undefined;
  return gtinCheckDigit(d.slice(0, -1)) === Number(d.slice(-1)) ? d : undefined;
}

/** Origem: integer string 0..8; blank = unset. */
export function normalizeOrigem(v: string | number | null | undefined): number | null | undefined {
  if (v == null || String(v).trim() === '') return null;
  const s = String(v).trim();
  if (!/^\d+$/.test(s)) return undefined;
  const n = Number(s);
  return n >= 0 && n <= 8 ? n : undefined;
}
