import { describe, expect, it } from 'vitest';

import { daysLabel, daysSince, displayPhone, filterQuery, fromDateInput, hasActiveFilters, splitTags, toDateInput } from './format';

describe('leads format', () => {
  const now = new Date(2026, 9, 26, 15, 0).getTime();

  it('counts whole calendar days since first contact, never negative', () => {
    expect(daysSince(new Date(2026, 9, 26, 1, 0).toISOString(), now)).toBe(0);
    expect(daysSince(new Date(2026, 9, 25, 23, 59).toISOString(), now)).toBe(1);
    expect(daysSince(new Date(2026, 9, 16, 12, 0).toISOString(), now)).toBe(10);
    expect(daysSince(new Date(2026, 10, 2).toISOString(), now)).toBe(0);
    expect(daysSince(null)).toBeNull();
    expect(daysSince('garbage')).toBeNull();
  });

  it('speaks pt-BR', () => {
    expect(daysLabel(0)).toBe('hoje');
    expect(daysLabel(1)).toBe('há 1 dia');
    expect(daysLabel(12)).toBe('há 12 dias');
    expect(daysLabel(null)).toBe('');
  });

  it('shows the canonical phone through the seed display seam, and keeps unparseable text visible', () => {
    expect(displayPhone('+5511994573387')).toBe('+5511994573387');
    expect(displayPhone('lixo')).toBe('lixo');
    expect(displayPhone(null)).toBe('');
  });

  it('sends only the filters that are set', () => {
    expect(filterQuery({ q: '  ana ', origin: '', from: '2026-01-01' })).toEqual({ q: 'ana', from: '2026-01-01' });
    expect(hasActiveFilters({})).toBe(false);
    expect(hasActiveFilters({ stage: 'lead' })).toBe(true);
  });

  it('round-trips a date input without shifting the calendar day', () => {
    expect(toDateInput(fromDateInput('2026-03-10'))).toBe('2026-03-10');
    expect(fromDateInput('')).toBeNull();
    expect(splitTags(' a, ,b ')).toEqual(['a', 'b']);
  });
});
