import { describe, expect, it } from 'vitest';
import { infiniteOps } from './infinite-ops';

const inf = (...pages: unknown[]) => ({ pages, pageParams: pages.map((_, i) => i) });

describe('infiniteOps', () => {
  it('patch / replace / remove find the row on any page of bare-array pages, keeping pageParams', () => {
    const d = inf([{ id: 'a' }], [{ id: 'b' }]);
    const p = infiniteOps.patch(d, 'b', { n: 1 })!;
    expect(p.pages[1]).toEqual([{ id: 'b', n: 1 }]);
    expect(p.pages[0]).toBe(d.pages[0]);
    expect(p.pageParams).toBe(d.pageParams);
    expect(infiniteOps.replace(d, 'a', { id: 'a', v: 2 })!.pages[0]).toEqual([{ id: 'a', v: 2 }]);
    expect(infiniteOps.remove(d, 'a')!.pages[0]).toEqual([]);
  });

  it('works on envelope pages (total moves on remove) and custom id keys', () => {
    const d = inf({ items: [{ slug: 's1' }], total: 2 }, { items: [{ slug: 's2' }], total: 2 });
    expect(infiniteOps.remove(d, 's2', 'slug')!.pages[1]).toEqual({ items: [], total: 1 });
    expect(infiniteOps.patch(d, 's1', { x: 1 }, 'slug')!.pages[0]).toEqual({ items: [{ slug: 's1', x: 1 }], total: 2 });
  });

  it('prepend puts a new row first on page 1 only; an existing row is replaced, not duplicated', () => {
    const d = inf([{ id: 'a' }], [{ id: 'b' }]);
    const out = infiniteOps.prepend(d, { id: 'n' })!;
    expect(out.pages[0]).toEqual([{ id: 'n' }, { id: 'a' }]);
    expect(out.pages[1]).toBe(d.pages[1]);
    expect(infiniteOps.prepend(d, { id: 'b', v: 1 })!.pages[1]).toEqual([{ id: 'b', v: 1 }]);
    const env = inf({ data: [{ id: 'a' }], pagination: { total: 1 } });
    expect(infiniteOps.prepend(env, { id: 'n' })!.pages[0]).toEqual({ data: [{ id: 'n' }, { id: 'a' }], pagination: { total: 2 } });
  });

  it('passes through uncached / non-infinite / unchanged', () => {
    const list = [{ id: 'a' }];
    expect(infiniteOps.patch(undefined, 'a', {})).toBeUndefined();
    expect(infiniteOps.remove(list, 'a')).toBe(list);
    const d = inf([{ id: 'a' }]);
    expect(infiniteOps.patch(d, 'zzz', {})).toBe(d);
  });
});

describe('infiniteOps — totals move on every page that carries one', () => {
  const pg = (ids: string[], total: number) => ({ items: ids.map((id) => ({ id })), total });
  it('remove: the page holding the row loses it and ALL pages drop the total by one', () => {
    const d = inf(pg(['a', 'b'], 5), pg(['c'], 5));
    const out = infiniteOps.remove(d, 'c')!;
    expect(out.pages.map((p: any) => p.total)).toEqual([4, 4]);
    expect((out.pages[1] as any).items).toEqual([]);
    expect(infiniteOps.remove(d, 'zzz')).toBe(d);
  });
  it('prepend: new row on page 1, every page total +1; existing row only replaced', () => {
    const d = inf(pg(['a'], 2), pg(['b'], 2));
    const out = infiniteOps.prepend(d, { id: 'n' })!;
    expect(out.pages.map((p: any) => p.total)).toEqual([3, 3]);
    expect((out.pages[0] as any).items[0]).toEqual({ id: 'n' });
    expect(infiniteOps.prepend(d, { id: 'b', x: 1 })!.pages.map((p: any) => p.total)).toEqual([2, 2]);
  });
  it('function idKey', () => {
    const d = inf([{ e: { id: 'a' } }]);
    expect(infiniteOps.remove(d, 'a', (r: any) => r.e.id)!.pages[0]).toEqual([]);
  });
});
