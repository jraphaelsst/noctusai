import { describe, expect, it } from 'vitest';

import { addTo, boardOps, patchById, removeById, rowOps } from '../cache-writes';

const ctx = { tempId: 't' };
const a = { id: 'a', n: 1 };
const b = { id: 'b', n: 2 };

describe('rowOps', () => {
  it('patches / removes / adds on a bare array', () => {
    expect(rowOps.patch([a, b], 'a', { n: 9 })).toEqual([{ id: 'a', n: 9 }, b]);
    expect(rowOps.remove([a, b], 'a')).toEqual([b]);
    expect(rowOps.add([a], b)).toEqual([a, b]);
    expect(rowOps.add([a], b, 'prepend')).toEqual([b, a]);
    expect(rowOps.add([a, b], b)).toEqual([a, b]);
  });
  it('keeps an envelope total honest (itens / items / data)', () => {
    expect(rowOps.remove({ itens: [a, b], total: 2 }, 'a')).toEqual({ itens: [b], total: 1 });
    expect(rowOps.remove({ itens: [a], total: 1 }, 'zz')).toEqual({ itens: [a], total: 1 });
    expect(rowOps.add({ items: [a], total: 1 }, b)).toEqual({ items: [a, b], total: 2 });
    expect(rowOps.add({ itens: [a], total: 1 }, a)).toEqual({ itens: [a], total: 1 });
    expect(rowOps.patch({ data: [a] }, 'a', { n: 5 })).toEqual({ data: [{ id: 'a', n: 5 }] });
  });
  it('patches a matching detail entity and ignores everything else', () => {
    expect(rowOps.patch(a, 'a', { n: 3 })).toEqual({ id: 'a', n: 3 });
    expect(rowOps.patch(b, 'a', { n: 3 })).toBe(b);
    expect(rowOps.remove(a, 'a')).toBe(a);
    expect(rowOps.add(a, b)).toBe(a);
    expect(rowOps.patch(undefined, 'a', {})).toBeUndefined();
  });
});

describe('target builders', () => {
  it('patchById draws the change and commits the server row under a prefix', () => {
    const t = patchById<{ id: string; n: number }, { id: string }>(['k'], (v) => v.id, () => ({ n: 7 }));
    expect(t.match).toBe('prefix');
    expect(t.optimistic!([a], { id: 'a' }, ctx)).toEqual([{ id: 'a', n: 7 }]);
    expect(t.commit!([a], { id: 'a', n: 8 }, { id: 'a' }, ctx)).toEqual([{ id: 'a', n: 8 }]);
  });
  it('removeById removes on the click; addTo commits into one exact list', () => {
    expect(removeById(['k'], (v: { id: string }) => v.id).optimistic!([a, b], { id: 'b' }, ctx)).toEqual([a]);
    const t = addTo<{ id: string }, void>(['k'], 'prepend');
    expect(t.match).toBeUndefined();
    expect(t.commit!([a], b, undefined, ctx)).toEqual([b, a]);
    expect(addTo<{ id: string }, void>(['k'], 'append', () => null).commit!([a], b, undefined, ctx)).toEqual([a]);
  });
});

describe('boardOps', () => {
  type Card = { id: string; v: number };
  const col = (etapa: string, cards: Card[]) => ({ etapa, total: cards.length, valorTotal: cards.reduce((s, c) => s + c.v, 0), cards });
  const ops = boardOps<Card>((c) => c.v);
  const board = () => [col('x', [{ id: '1', v: 10 }, { id: '2', v: 5 }]), col('y', [{ id: '3', v: 1 }])];

  it('patchCard moves valorTotal by the delta', () => {
    const out = ops.patchCard(board(), '1', { v: 20 })!;
    expect(out[0].valorTotal).toBe(25);
    expect(out[0].cards[0]).toEqual({ id: '1', v: 20 });
  });
  it('removeCard drops the card and its total/value', () => {
    const out = ops.removeCard(board(), '2')!;
    expect(out[0]).toMatchObject({ total: 1, valorTotal: 10 });
  });
  it('addCard puts it on top of the stage, only once, only when the stage exists', () => {
    const out = ops.addCard(board(), 'y', { id: '9', v: 4 })!;
    expect(out[1]).toMatchObject({ total: 2, valorTotal: 5 });
    expect(out[1].cards[0].id).toBe('9');
    expect(ops.addCard(board(), 'nope', { id: '9', v: 4 })).toEqual(board());
    expect(ops.addCard(board(), 'y', { id: '1', v: 4 })).toEqual(board());
  });
  it('moveCard crosses columns (totals follow, capped totals stay true) and reorders within one', () => {
    const capped = [{ ...col('x', [{ id: '1', v: 10 }]), total: 50, valorTotal: 500 }, col('y', [{ id: '3', v: 1 }])];
    const out = ops.moveCard(capped, '1', 'y', 1)!;
    expect(out[0]).toMatchObject({ cards: [], total: 49, valorTotal: 490 });
    expect(out[1].cards.map((c) => c.id)).toEqual(['3', '1']);
    expect(out[1]).toMatchObject({ total: 2, valorTotal: 11 });
    const same = ops.moveCard(board(), '1', 'x', 1)!;
    expect(same[0].cards.map((c) => c.id)).toEqual(['2', '1']);
    expect(same[0]).toMatchObject({ total: 2, valorTotal: 15 });
    expect(ops.moveCard(board(), '1', 'y')![1].cards[0].id).toBe('1');
    expect(ops.moveCard(board(), 'zz', 'y')).toEqual(board());
    expect(ops.moveCard(board(), '1', 'nope')).toEqual(board());
    expect(ops.moveCard(undefined, '1', 'y')).toBeUndefined();
  });
});

describe('boardOps — columns without aggregates', () => {
  type C = { id: string };
  const ops = boardOps<C>(() => 0);
  it('never writes NaN: only aggregates that exist move', () => {
    const board = [{ etapa: 'a', cards: [{ id: '1' }] }, { etapa: 'b', total: 3, cards: [] }];
    const moved = ops.moveCard(board, '1', 'b') as any[];
    expect(moved[0]).not.toHaveProperty('total');
    expect(moved[0]).not.toHaveProperty('valorTotal');
    expect(moved[1].total).toBe(4);
    expect(moved[1]).not.toHaveProperty('valorTotal');
    const added = ops.addCard(board, 'a', { id: '2' }) as any[];
    expect(added[0].cards).toHaveLength(2);
    expect(Object.values(added[0]).some((x) => Number.isNaN(x))).toBe(false);
    expect((ops.removeCard(board, '1') as any[])[0]).not.toHaveProperty('valorTotal');
    expect((ops.patchCard(board, '1', { z: 1 }) as any[])[0]).not.toHaveProperty('valorTotal');
  });
});

describe('boardOps — shared-prefix entries that are not boards', () => {
  it('a stage list (no cards) passes through untouched', () => {
    const ops = boardOps<{ id: string }>(() => 0);
    const stages = [{ etapa: 'a' }, { etapa: 'b' }];
    expect(ops.patchCard(stages, '1', {})).toBe(stages);
    expect(ops.removeCard(stages, '1')).toBe(stages);
    expect(ops.moveCard(stages, '1', 'b')).toBe(stages);
    expect(ops.addCard(stages, 'a', { id: '1' })).toBe(stages);
  });
});
