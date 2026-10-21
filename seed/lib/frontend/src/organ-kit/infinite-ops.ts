/**
 * `infiniteOps` — pure edits for `useInfiniteQuery` caches: `{ pages: Page[], pageParams: unknown[] }`, where a
 * page is a bare array of rows or a `pageOps` envelope (`{ data | items | itens: T[], total? }`).
 *
 * `pageParams` and every untouched page keep their identity (cursors stay valid). Same safety rules as
 * `listOps`: `undefined` and anything that is not an infinite cache come back unchanged, so a `match: 'prefix'`
 * target is safe. Rows are addressed by `id` unless the trailing `idKey` says otherwise.
 *
 * KB § PATTERNS/frontend/mutation-cache-writes.md
 */
import { idOf, pageOps, withTotal, type IdKey } from './page-ops';

type Row = Record<string, unknown>;
export type InfiniteData<P = unknown> = { pages: P[]; pageParams: unknown[] };

const isInfinite = (v: unknown): v is InfiniteData =>
  !!v && typeof v === 'object' && Array.isArray((v as InfiniteData).pages);

/** Apply `fn` to every page; the cache object is only rebuilt when some page changed. */
function mapPages<D>(data: D | undefined, fn: (page: unknown, index: number) => unknown): D | undefined {
  if (!isInfinite(data)) return data;
  let changed = false;
  const pages = data.pages.map((p, i) => {
    const next = fn(p, i);
    if (next !== p) changed = true;
    return next;
  });
  return changed ? ({ ...data, pages } as D) : data;
}

const holds = (data: InfiniteData, id: unknown, idKey: IdKey) =>
  data.pages.some((p) => (Array.isArray(p) ? (p as Row[]).some((r) => idOf(r, idKey) === id) : pageOps.patch(p, id as string | number, {}, idKey) !== p));

export const infiniteOps = {
  mapPages,
  /** Merge `changes` into the row `id` wherever it sits across the loaded pages. */
  patch<D>(data: D | undefined, id: string | number, changes: object, idKey: IdKey = 'id'): D | undefined {
    return mapPages(data, (p) =>
      Array.isArray(p)
        ? (p as Row[]).some((r) => idOf(r, idKey) === id)
          ? (p as Row[]).map((r) => (idOf(r, idKey) === id ? { ...r, ...changes } : r))
          : p
        : pageOps.patch(p, id, changes, idKey),
    );
  },
  /** Replace the row `id` by the server's `row` wherever it sits. */
  replace<D>(data: D | undefined, id: string | number, row: object, idKey: IdKey = 'id'): D | undefined {
    return mapPages(data, (p) =>
      Array.isArray(p)
        ? (p as Row[]).some((r) => idOf(r, idKey) === id)
          ? (p as Row[]).map((r) => (idOf(r, idKey) === id ? (row as Row) : r))
          : p
        : pageOps.replace(p, id, row, idKey),
    );
  },
  /**
   * Drop the row `id` from whichever page holds it. Every envelope page that carries a `total` moves it by one
   * together (not just the page that held the row): the total describes the WHOLE list and each page repeats it,
   * so a list reading it from its last (or first) page must not lag by one. Bare-array pages carry no total.
   */
  remove<D>(data: D | undefined, id: string | number, idKey: IdKey = 'id'): D | undefined {
    if (!isInfinite(data) || !holds(data, id, idKey)) return data;
    return mapPages(data, (p) =>
      Array.isArray(p)
        ? (p as Row[]).some((r) => idOf(r, idKey) === id)
          ? (p as Row[]).filter((r) => idOf(r, idKey) !== id)
          : p
        : pageOps.patch(p, id, {}, idKey) !== p
          ? pageOps.remove(p, id, idKey)
          : withTotal(p, -1),
    );
  },
  /**
   * Put a NEW row first on the FIRST page (newest-first feeds); every page's `total` moves by one. A row already on any page is replaced in
   * place instead (never duplicated). Other pages are left alone — they shift server-side and converge on settle.
   */
  prepend<D>(data: D | undefined, row: object, idKey: IdKey = 'id'): D | undefined {
    if (!isInfinite(data) || data.pages.length === 0) return data;
    const id = idOf(row, idKey) as string | number;
    if (holds(data, id, idKey)) return infiniteOps.replace(data, id, row, idKey);
    // Every envelope page's total moves with the new row (see `remove`).
    return mapPages(data, (p, i) => (i !== 0 ? withTotal(p, 1) : Array.isArray(p) ? [row, ...p] : pageOps.add(p, row, 'prepend', idKey)));
  },
};
