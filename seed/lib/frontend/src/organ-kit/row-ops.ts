/**
 * `rowOps` / `boardOps` + target builders — cache edits for the shapes a product's queries hold when ONE
 * `match: 'prefix'` target must edit a row wherever it is cached:
 *
 *   - a bare array of rows;
 *   - a paged / small envelope (`{ data | items | itens: T[], total? }` — see `pageOps`);
 *   - a single entity (a detail query) addressed by the same row id.
 *
 * Anything that is none of these passes through unchanged (and `undefined` stays `undefined`), so a prefix target
 * leaves every other entry alone. `boardOps` does the same for the pipeline organ's board cache
 * (`PipelineColumn[]`: `{ etapa, total, valorTotal, cards }`), including moving a card between columns.
 *
 * Imported from `cache-writes` (the one home for cache edits); this file only imports TYPES from it.
 *
 * KB § PATTERNS/frontend/mutation-cache-writes.md
 */
import type { QueryKey } from '@tanstack/react-query';

import type { CacheWriteTarget } from '../cache-writes';
import { pageOps } from './page-ops';

type Row = { id: string };

const isEntity = (x: unknown, id: string): x is Row =>
  !!x && typeof x === 'object' && !Array.isArray(x) && (x as Row).id === id;

/** Row edits that work on a list, an envelope or a detail entity. */
export const rowOps = {
  patch<T>(old: T | undefined, id: string, changes: object): T | undefined {
    if (Array.isArray(old)) return (old as Row[]).map((r) => (r.id === id ? { ...r, ...changes } : r)) as T;
    const paged = pageOps.patch(old, id, changes);
    if (paged !== old) return paged;
    if (isEntity(old, id)) return { ...old, ...changes } as T;
    return old;
  },
  remove<T>(old: T | undefined, id: string): T | undefined {
    if (Array.isArray(old)) return (old as Row[]).filter((r) => r.id !== id) as T;
    return pageOps.remove(old, id);
  },
  /** Add `row` to a list / envelope unless it is already there (a refetch may have won the race). */
  add<T>(old: T | undefined, row: Row, where: 'append' | 'prepend' = 'append'): T | undefined {
    if (Array.isArray(old)) {
      if ((old as Row[]).some((r) => r.id === row.id)) return old;
      return (where === 'prepend' ? [row, ...(old as Row[])] : [...(old as Row[]), row]) as T;
    }
    return pageOps.add(old, row, where);
  },
};

/** Patch row `idOf(vars)` everywhere under `queryKey`: draw `changesOf(vars)` now, commit the server's row. */
export function patchById<TData extends Row, TVars>(
  queryKey: QueryKey,
  idOf: (vars: TVars) => string,
  changesOf?: (vars: TVars) => object,
  rowOf: (saved: TData) => Row & object = (saved) => saved,
): CacheWriteTarget<TData, TVars> {
  return {
    queryKey,
    match: 'prefix',
    optimistic: changesOf ? (old, vars) => rowOps.patch(old, idOf(vars), changesOf(vars)) : undefined,
    commit: (old, saved) => {
      const row = rowOf(saved);
      return rowOps.patch(old, row.id, row);
    },
  };
}

/** Remove row `idOf(vars)` from everything under `queryKey` on the click. */
export function removeById<TData, TVars>(queryKey: QueryKey, idOf: (vars: TVars) => string): CacheWriteTarget<TData, TVars> {
  return { queryKey, match: 'prefix', optimistic: (old, vars) => rowOps.remove(old, idOf(vars)) };
}

/** Put the server's new row into ONE exact list (the one it certainly belongs in). */
export function addTo<TData extends Row, TVars>(
  queryKey: QueryKey,
  where: 'append' | 'prepend' = 'append',
  rowOf: (saved: TData) => Row | null = (saved) => saved,
): CacheWriteTarget<TData, TVars> {
  return {
    queryKey,
    commit: (old, saved) => {
      const row = rowOf(saved);
      return row ? rowOps.add(old, row, where) : old;
    },
  };
}

type Column = { etapa: string; total?: number; valorTotal?: number; cards: Array<{ id: string }> };

/** A board cache is an array of columns that all carry `cards`; stage-list entries sharing the prefix are not boards. */
const isBoard = (old: unknown): old is Column[] => Array.isArray(old) && old.every((c) => Array.isArray(c?.cards));

/** Move a column's aggregates, only those it actually has (a board without `valorTotal` must not grow a NaN). */
const adj = (col: Column, dTotal: number, dValor: number): Column => ({
  ...col,
  ...(typeof col.total === 'number' ? { total: Math.max(0, col.total + dTotal) } : {}),
  ...(typeof col.valorTotal === 'number' ? { valorTotal: col.valorTotal + dValor } : {}),
});

/** Board (`PipelineColumn[]`) edits. `valueOf` is the descriptor's `getCardValue`; `idOf` its `getCardId` (default `.id`). */
export function boardOps<TCard>(valueOf: (card: TCard) => number, idOf: (card: TCard) => string = (c) => (c as unknown as Row).id) {
  const v = (c: unknown) => Number(valueOf(c as TCard) || 0);
  const id = (c: unknown) => idOf(c as TCard);
  return {
    patchCard<T>(old: T | undefined, cardId: string, changes: object): T | undefined {
      if (!isBoard(old)) return old;
      return (old as Column[]).map((col) => {
        const at = col.cards.findIndex((c) => id(c) === cardId);
        if (at === -1) return col;
        const before = col.cards[at];
        const after = { ...before, ...changes };
        const cards = col.cards.map((c, i) => (i === at ? after : c));
        return { ...adj(col, 0, v(after) - v(before)), cards };
      }) as T;
    },
    removeCard<T>(old: T | undefined, cardId: string): T | undefined {
      if (!isBoard(old)) return old;
      return (old as Column[]).map((col) => {
        const card = col.cards.find((c) => id(c) === cardId);
        if (!card) return col;
        return { ...adj(col, -1, -v(card)), cards: col.cards.filter((c) => id(c) !== cardId) };
      }) as T;
    },
    /** Put `card` on top of the column of stage `etapaId` (no-op when absent or the stage is not on this board). */
    addCard<T>(old: T | undefined, etapaId: string, card: TCard): T | undefined {
      if (!isBoard(old)) return old;
      const cols = old as Column[];
      if (cols.some((c) => c.cards.some((x) => id(x) === id(card))) || !cols.some((c) => c.etapa === etapaId)) return old;
      return cols.map((col) =>
        col.etapa === etapaId ? { ...adj(col, 1, v(card)), cards: [card as unknown as Row, ...col.cards] } : col,
      ) as T;
    },
    /**
     * Move card `cardId` to stage `toEtapa` (at `toIndex`, else on top). Both columns' `total` / `valorTotal` move by
     * the card (so a column capped by `exibidos` keeps its true totals). No-op when the card or the target stage
     * is not on this board.
     */
    moveCard<T>(old: T | undefined, cardId: string, toEtapa: string, toIndex?: number): T | undefined {
      if (!isBoard(old)) return old;
      const cols = old as Column[];
      const from = cols.find((c) => c.cards.some((x) => id(x) === cardId));
      if (!from || !cols.some((c) => c.etapa === toEtapa)) return old;
      const card = from.cards.find((x) => id(x) === cardId)!;
      const crossing = from.etapa !== toEtapa;
      return cols.map((col) => {
        const isFrom = col === from;
        const isTo = col.etapa === toEtapa;
        if (!isFrom && !isTo) return col;
        let cards = isFrom ? col.cards.filter((x) => id(x) !== cardId) : col.cards;
        if (isTo) {
          const at = toIndex === undefined ? 0 : Math.max(0, Math.min(toIndex, cards.length));
          cards = [...cards.slice(0, at), card, ...cards.slice(at)];
        }
        if (!crossing) return { ...col, cards };
        return isFrom
          ? { ...adj(col, -1, -v(card)), cards }
          : { ...adj(col, 1, v(card)), cards };
      }) as T;
    },
  };
}
