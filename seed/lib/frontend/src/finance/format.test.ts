import { describe, it, expect } from 'vitest';
import { buildQuery, formatBytes, formatDate, formatMonth, monthEndIso, monthStartIso, remainingCents, toCompetenceMonth, todayIso } from './format';
import { centsToInput, formatCents, parseMoneyToCents } from './format';

describe('finance format', () => {
  it('reuses the commerce money seam (integer cents)', () => {
    expect(formatCents(123456).replace(/\s/g, ' ')).toBe('R$ 1.234,56');
    expect(parseMoneyToCents('1.234,56')).toBe(123456);
    expect(centsToInput(1250)).toBe('12,50');
  });
  it('formats date-only values without a timezone shift', () => {
    expect(formatDate('2026-10-14')).toBe('14/10/2026');
    expect(formatDate(null)).toBe('—');
    expect(formatMonth('2026-10-01')).toBe('out/2026');
    expect(formatMonth('2026-03')).toBe('mar/2026');
  });
  it('month helpers', () => {
    const now = new Date(2026, 9, 14);
    expect(todayIso(now)).toBe('2026-10-14');
    expect(monthStartIso(now)).toBe('2026-10-01');
    expect(monthEndIso(now)).toBe('2026-10-31');
    expect(monthEndIso(now, 5)).toBe('2027-03-31');
    expect(toCompetenceMonth('2026-10-20')).toBe('2026-10-01');
  });
  it('remainingCents never goes negative', () => {
    expect(remainingCents({ amount_cents: 100, settled_cents: 30 })).toBe(70);
    expect(remainingCents({ amount_cents: 100, settled_cents: 130 })).toBe(0);
  });
  it('buildQuery drops empties', () => {
    expect(buildQuery({ a: 1, b: '', c: undefined, d: 'x y' })).toBe('?a=1&d=x+y');
    expect(buildQuery({})).toBe('');
  });
  it('formatBytes', () => {
    expect(formatBytes(512)).toBe('512 B');
    expect(formatBytes(2048)).toBe('2,0 KB');
  });
});
