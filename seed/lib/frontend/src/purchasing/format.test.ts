import { describe, expect, it } from 'vitest';
import { formatDate, lineTotalCents, newIdempotencyKey, qtyToWire } from './format';

describe('purchasing format', () => {
  it('line total is round(qty x cost) like the server (half away from zero)', () => {
    expect(lineTotalCents('2.5', 333)).toBe(833); // 832.5 -> 833
    expect(lineTotalCents(10, 1000)).toBe(10000);
    expect(lineTotalCents('x', 100)).toBe(0);
  });
  it('dates are calendar dates, never shifted by timezone', () => {
    expect(formatDate('2026-10-14')).toBe('14/10/2026');
    expect(formatDate('2026-10-14T23:59:00-03:00')).toBe('14/10/2026');
    expect(formatDate(null)).toBe('—');
  });
  it('quantities go on the wire with at most 3 places and no trailing zeros', () => {
    expect(qtyToWire(10)).toBe('10');
    expect(qtyToWire(2.5)).toBe('2.5');
    expect(qtyToWire(0.1 + 0.2)).toBe('0.3');
  });
  it('idempotency keys are unique per call', () => {
    expect(newIdempotencyKey()).not.toBe(newIdempotencyKey());
  });
});
