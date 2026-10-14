import { describe, it, expect } from 'vitest';
import { bpToPercent, formatDate, hoursToMinutes, linesTotal, minutesToHours, percentToBp } from './format';

describe('contracts format', () => {
  it('dates are cut, never time-zone shifted', () => {
    expect(formatDate('2026-11-10')).toBe('10/11/2026');
    expect(formatDate('2026-11-10T00:00:00+00:00')).toBe('10/11/2026');
    expect(formatDate(null)).toBe('—');
  });
  it('percent <-> basis points', () => {
    expect(percentToBp('4,5')).toBe(450);
    expect(percentToBp('4.50%')).toBe(450);
    expect(percentToBp('0,01')).toBe(1);
    expect(percentToBp('-1')).toBeNull();
    expect(percentToBp('abc')).toBeNull();
    expect(percentToBp('1001')).toBeNull();
    expect(bpToPercent(450)).toBe('4,50');
  });
  it('hours <-> minutes', () => {
    expect(hoursToMinutes('10')).toBe(600);
    expect(hoursToMinutes('1,5')).toBe(90);
    expect(hoursToMinutes('x')).toBeNull();
    expect(minutesToHours(600)).toBe('10');
    expect(minutesToHours(90)).toBe('1,5');
  });
  it('lines total is integer cents', () => {
    expect(linesTotal([{ quantity: 2, unit_price_cents: 50000 }, { quantity: 1, unit_price_cents: 5 }])).toBe(100005);
  });
});
