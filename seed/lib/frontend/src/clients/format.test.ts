import { describe, expect, it } from 'vitest';

import {
  addDays,
  clientsFilterQuery,
  formatWhen,
  optionOf,
  paymentStatusOf,
  todayIn,
  weekdayOf,
  weekStartOf,
  zonedIso,
  zonedParts,
} from './format';

const SP = 'America/Sao_Paulo';

describe('zone helpers', () => {
  it('reads an instant in the org zone, not the browser zone', () => {
    expect(zonedParts('2026-11-03T17:00:00Z', SP)).toEqual({ date: '2026-11-03', time: '14:00', weekday: 1 });
    // 01:30 UTC is still the previous evening in São Paulo.
    expect(zonedParts('2026-11-04T01:30:00Z', SP)).toEqual({ date: '2026-11-03', time: '22:30', weekday: 1 });
    expect(zonedParts('nope', SP)).toBeNull();
  });

  it('turns a typed date + time into an ISO instant with the zone offset (round-trips)', () => {
    const iso = zonedIso('2026-11-03', '14:00', SP)!;
    expect(iso).toBe('2026-11-03T14:00:00-03:00');
    expect(zonedParts(iso, SP)).toMatchObject({ date: '2026-11-03', time: '14:00' });
    expect(zonedIso('2026-11-03T00', '14:00', SP)).toBeNull();
    expect(zonedIso('2026-11-03', '', SP)).toBeNull();
    expect(zonedIso('2026-07-01', '09:30', 'UTC')).toBe('2026-07-01T09:30:00+00:00');
  });

  it('today is the zone calendar day', () => {
    expect(todayIn(SP, Date.parse('2026-11-04T01:30:00Z'))).toBe('2026-11-03');
  });

  it('week arithmetic: Monday-based weeks', () => {
    expect(weekdayOf('2026-11-02')).toBe(0); // a Monday
    expect(weekdayOf('2026-11-08')).toBe(6);
    expect(weekStartOf('2026-11-05')).toBe('2026-11-02');
    expect(weekStartOf('2026-11-08')).toBe('2026-11-02');
    expect(addDays('2026-12-30', 3)).toBe('2027-01-02');
  });

  it('formats a session moment as weekday, date and time', () => {
    expect(formatWhen('2026-11-03T14:00:00-03:00', SP)).toBe('ter, 03/11/2026 14:00');
    expect(formatWhen(null, SP)).toBe('');
  });
});

describe('labels and filters', () => {
  it('an unknown status degrades to its slug with a neutral colour', () => {
    expect(optionOf([{ slug: 'ativo', label: 'Ativo', color: 'success' }], 'x')).toEqual({ slug: 'x', label: 'x', color: null });
  });

  it('payment status from the receivable', () => {
    const e = { entry_id: 'e', session_id: 's', description: '', amount_cents: 100, settled_cents: 0, due_date: '2026-11-03', status: 'open', overdue: false };
    expect(paymentStatusOf(undefined)).toBe('none');
    expect(paymentStatusOf(e)).toBe('open');
    expect(paymentStatusOf({ ...e, settled_cents: 40 })).toBe('partial');
    expect(paymentStatusOf({ ...e, overdue: true })).toBe('overdue');
    expect(paymentStatusOf({ ...e, settled_cents: 100, overdue: true })).toBe('paid');
    expect(paymentStatusOf({ ...e, status: 'cancelled' })).toBe('none');
  });

  it('empty filters are not sent', () => {
    expect(clientsFilterQuery({ q: '  ', status: '', tag: 'vip' })).toEqual({ tag: 'vip' });
  });
});
