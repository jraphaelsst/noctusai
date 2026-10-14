/** Document helpers for the parties organ (display only — the server is the validator of record). */
import { cnpjDvValido, cpfDvValido } from '../identificador';
import type { PartyKind } from './types';

/** Alphanumeric uppercase only (CNPJ may carry letters since 2026). */
export function onlyAlnum(s: string): string {
  return s.replace(/[^0-9A-Za-z]/g, '').toUpperCase();
}

/** The server masks a document for non-admin readers: any `*` means "not the real value". */
export function isMaskedDoc(doc: string | null | undefined): boolean {
  return !!doc && doc.includes('*');
}

/** Progressive `000.000.000-00` / `00.000.000/0000-00` mask for the input of the given kind. */
export function maskDocInput(kind: PartyKind, value: string): string {
  const d = onlyAlnum(value).slice(0, kind === 'PF' ? 11 : 14);
  if (kind === 'PF') {
    let out = d.slice(0, 3);
    if (d.length > 3) out += '.' + d.slice(3, 6);
    if (d.length > 6) out += '.' + d.slice(6, 9);
    if (d.length > 9) out += '-' + d.slice(9, 11);
    return out;
  }
  let out = d.slice(0, 2);
  if (d.length > 2) out += '.' + d.slice(2, 5);
  if (d.length > 5) out += '.' + d.slice(5, 8);
  if (d.length > 8) out += '/' + d.slice(8, 12);
  if (d.length > 12) out += '-' + d.slice(12, 14);
  return out;
}

/** Display form of a STORED document (already masked by the server for staff — passed through untouched). */
export function formatDoc(kind: PartyKind, doc: string | null | undefined): string {
  if (!doc) return '';
  return isMaskedDoc(doc) ? doc : maskDocInput(kind, doc);
}

/** CPF (PF, 11 digits) / CNPJ (PJ, 14 numeric or alphanumeric) with valid check digits. Blank is valid (doc is optional). */
export function isValidDoc(kind: PartyKind, value: string): boolean {
  const d = onlyAlnum(value);
  if (!d) return true;
  if (kind === 'PF') return d.length === 11 && /^\d+$/.test(d) && cpfDvValido(d);
  return d.length === 14 && cnpjDvValido(d);
}

export function isValidEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(value.trim());
}

/** Splits a free "phones" input (comma / semicolon / newline separated) into non-empty entries. */
export function splitPhones(input: string): string[] {
  return input.split(/[,;\n]/).map((p) => p.trim()).filter(Boolean);
}
