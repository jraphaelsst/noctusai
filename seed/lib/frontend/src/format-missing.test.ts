import { describe, it, expect } from 'vitest';
import { formatCurrency } from './utils';
import { formatCents, centsToInput } from './organ-kit/money';
import { formatQty } from './inventory/format';
import { formatCompactNumber } from './design-system/charts/formatters';

// A missing value is not zero (frontend-craft-canon §8): "—", never R$ 0,00 / 0.
describe('missing values render "—"', () => {
  it('formatCurrency', () => {
    expect(formatCurrency(null)).toBe('—');
    expect(formatCurrency(undefined)).toBe('—');
    expect(formatCurrency(NaN)).toBe('—');
    expect(formatCurrency(0).replace(/\s/g, ' ')).toBe('R$ 0,00'); // a real zero stays a zero
  });
  it('formatCents', () => {
    expect(formatCents(null)).toBe('—');
    expect(formatCents(undefined)).toBe('—');
    expect(formatCents(0).replace(/\s/g, ' ')).toBe('R$ 0,00');
  });
  it('formatQty', () => {
    expect(formatQty(null)).toBe('—');
    expect(formatQty('')).toBe('—');
    expect(formatQty(0)).toBe('0');
  });
  it('formatCompactNumber', () => {
    expect(formatCompactNumber(null)).toBe('—');
    expect(formatCompactNumber(0)).toBe('0');
  });
  it('centsToInput stays empty for null', () => {
    expect(centsToInput(null)).toBe('');
  });
});
