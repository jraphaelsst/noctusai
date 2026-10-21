import { describe, expect, it } from 'vitest';
import { pageOps } from './page-ops';

const data = (rows: { id: string; n?: number }[], total = rows.length, page = 1) => ({ data: rows, pagination: { page, page_size: 2, total } });
const items = (rows: { id: string }[], total = rows.length, page = 1) => ({ items: rows, page, page_size: 2, total });

describe('pageOps (the paginated envelopes of the organs)', () => {
  it('patch / replace edit a row on the page, in both envelope shapes; a row not on the page is a no-op', () => {
    expect(pageOps.patch(data([{ id: 'a' }, { id: 'b' }]), 'b', { n: 2 })?.data[1]).toEqual({ id: 'b', n: 2 });
    expect(pageOps.replace(items([{ id: 'a' }]), 'a', { id: 'a', x: 1 })?.items[0]).toEqual({ id: 'a', x: 1 });
    const p = data([{ id: 'a' }]);
    expect(pageOps.patch(p, 'zzz', { n: 1 })).toBe(p);
  });

  it('remove takes one off the total wherever it lives', () => {
    expect(pageOps.remove(data([{ id: 'a' }, { id: 'b' }], 7), 'a')).toMatchObject({ data: [{ id: 'b' }], pagination: { total: 6 } });
    expect(pageOps.remove(items([{ id: 'a' }, { id: 'b' }], 7), 'a')).toMatchObject({ items: [{ id: 'b' }], total: 6 });
  });

  it('supports another id key', () => {
    const p = { items: [{ user_id: 'u1' }, { user_id: 'u2' }], total: 2 };
    expect(pageOps.remove(p, 'u1', 'user_id')).toEqual({ items: [{ user_id: 'u2' }], total: 1 });
  });

  it('prependNewest puts a new row first on page 1 only, trims to page_size, bumps the total, never duplicates', () => {
    expect(pageOps.prependNewest(items([{ id: 'a' }, { id: 'b' }], 2), { id: 'n' })).toEqual({ items: [{ id: 'n' }, { id: 'a' }], page: 1, page_size: 2, total: 3 });
    expect(pageOps.prependNewest(data([{ id: 'a' }], 1), { id: 'n' })?.data.map((r) => r.id)).toEqual(['n', 'a']);
    const later = items([{ id: 'c' }], 3, 2);
    expect(pageOps.prependNewest(later, { id: 'n' })).toBe(later);
    expect(pageOps.prependNewest(items([{ id: 'a' }]), { id: 'a', v: 2 })).toMatchObject({ items: [{ id: 'a', v: 2 }], total: 1 });
  });

  it('leaves uncached entries, details and bare arrays untouched', () => {
    const detail = { id: 'a', name: 'x' };
    const list = [{ id: 'a' }];
    expect(pageOps.patch(undefined, 'a', {})).toBeUndefined();
    expect(pageOps.remove(detail, 'a')).toBe(detail);
    expect(pageOps.replace(list, 'a', { id: 'a' })).toBe(list);
    expect(pageOps.prependNewest(detail, { id: 'n' })).toBe(detail);
  });
});
