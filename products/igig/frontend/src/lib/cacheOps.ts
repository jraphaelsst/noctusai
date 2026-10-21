/**
 * Cache edits igig's mutation hooks share — built on the seed's `listOps`
 * (`@noctusai/lib/cache-writes`), extended to the three cache shapes igig's
 * queries actually hold:
 *
 *   - a bare array of rows (`unwrapData<T[]>` lists);
 *   - an `{ itens: T[], total? }` envelope (clientes, cofre, calendário);
 *   - a single entity (a detail query) addressed by the same row id;
 *
 * so ONE prefix target (`{ queryKey: [FAMILY], match: 'prefix' }`) edits the
 * row wherever it is cached — every filtered list AND its detail — and leaves
 * every other entry alone (anything that is none of the three passes through).
 *
 * `boardOps` does the same for the seed pipeline organ's board cache
 * (`PipelineColumn[]`: `{ etapa, total, valorTotal, cards }`).
 *
 * KB § PATTERNS/frontend/mutation-cache-writes.md
 */
import { listOps, type CacheWriteTarget } from "@noctusai/lib/cache-writes";
import type { QueryKey } from "@tanstack/react-query";

type Row = { id: string };
type Envelope = { itens: Row[]; total?: number };

function isEnvelope(x: unknown): x is Envelope {
  return !!x && typeof x === "object" && !Array.isArray(x) && Array.isArray((x as Envelope).itens);
}

function isEntity(x: unknown, id: string): x is Row {
  return !!x && typeof x === "object" && !Array.isArray(x) && (x as Row).id === id;
}

function bump(total: number | undefined, delta: number): number | undefined {
  return typeof total === "number" ? Math.max(0, total + delta) : total;
}

/** Row edits that work on a list, an `{itens}` envelope or a detail entity. */
export const rowOps = {
  patch<T>(old: T | undefined, id: string, changes: object): T | undefined {
    if (Array.isArray(old)) return listOps.patch(old as Row[], id, changes) as T;
    if (isEnvelope(old)) return { ...old, itens: listOps.patch(old.itens, id, changes) } as T;
    if (isEntity(old, id)) return { ...old, ...changes } as T;
    return old;
  },
  remove<T>(old: T | undefined, id: string): T | undefined {
    if (Array.isArray(old)) return listOps.remove(old as Row[], id) as T;
    if (isEnvelope(old)) {
      const had = old.itens.some((r) => r.id === id);
      return { ...old, itens: listOps.remove(old.itens, id), total: bump(old.total, had ? -1 : 0) } as T;
    }
    return old;
  },
  /** Add `row` to a list / envelope unless it is already there (a refetch may have won the race). */
  add<T>(old: T | undefined, row: Row, where: "append" | "prepend" = "append"): T | undefined {
    const put = (list: Row[]) => (list.some((r) => r.id === row.id) ? list : where === "prepend" ? [row, ...list] : [...list, row]);
    if (Array.isArray(old)) return put(old as Row[]) as T;
    if (isEnvelope(old)) {
      const had = old.itens.some((r) => r.id === row.id);
      return { ...old, itens: put(old.itens), total: bump(old.total, had ? 0 : 1) } as T;
    }
    return old;
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
    match: "prefix",
    optimistic: changesOf ? (old, vars) => rowOps.patch(old, idOf(vars), changesOf(vars)) : undefined,
    commit: (old, saved) => {
      const row = rowOf(saved);
      return rowOps.patch(old, row.id, row);
    },
  };
}

/** Remove row `idOf(vars)` from everything under `queryKey` on the click. */
export function removeById<TData, TVars>(queryKey: QueryKey, idOf: (vars: TVars) => string): CacheWriteTarget<TData, TVars> {
  return { queryKey, match: "prefix", optimistic: (old, vars) => rowOps.remove(old, idOf(vars)) };
}

/** Put the server's new row into ONE exact list (the one it certainly belongs in). */
export function addTo<TData extends Row, TVars>(
  queryKey: QueryKey,
  where: "append" | "prepend" = "append",
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

type Column = { etapa: string; total: number; valorTotal: number; cards: Array<{ id: string }> };

/** Board (`PipelineColumn[]`) edits. `valueOf` is the descriptor's `getCardValue`. */
export function boardOps<TCard extends { id: string }>(valueOf: (card: TCard) => number) {
  const v = (c: unknown) => Number(valueOf(c as TCard) || 0);
  return {
    patchCard<T>(old: T | undefined, id: string, changes: object): T | undefined {
      if (!Array.isArray(old)) return old;
      return (old as Column[]).map((col) => {
        const at = col.cards.findIndex((c) => c.id === id);
        if (at === -1) return col;
        const before = col.cards[at];
        const after = { ...before, ...changes };
        const cards = col.cards.map((c, i) => (i === at ? after : c));
        return { ...col, cards, valorTotal: col.valorTotal + v(after) - v(before) };
      }) as T;
    },
    removeCard<T>(old: T | undefined, id: string): T | undefined {
      if (!Array.isArray(old)) return old;
      return (old as Column[]).map((col) => {
        const card = col.cards.find((c) => c.id === id);
        if (!card) return col;
        return { ...col, cards: col.cards.filter((c) => c.id !== id), total: Math.max(0, col.total - 1), valorTotal: col.valorTotal - v(card) };
      }) as T;
    },
    /** Put `card` on top of the column of stage `etapaId` (no-op when absent or the stage is not on this board). */
    addCard<T>(old: T | undefined, etapaId: string, card: TCard): T | undefined {
      if (!Array.isArray(old)) return old;
      const cols = old as Column[];
      if (cols.some((c) => c.cards.some((x) => x.id === card.id)) || !cols.some((c) => c.etapa === etapaId)) return old;
      return cols.map((col) =>
        col.etapa === etapaId ? { ...col, cards: [card, ...col.cards], total: col.total + 1, valorTotal: col.valorTotal + v(card) } : col,
      ) as T;
    },
  };
}
