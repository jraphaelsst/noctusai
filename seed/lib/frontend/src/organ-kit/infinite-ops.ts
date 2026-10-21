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
import { pageOps } from './page-ops';

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

export const infiniteOps = {
  mapPages,
  /** Merge `changes` into the row `id` wherever it sits across the loaded pages. */
  patch<D>(data: D | undefined, id: string | number, changes: object, idKey = 'id'): D | undefined {
    return mapPages(data, (p) =>
      Array.isArray(p)
        ? (p as Row[]).some((r) => r[idKey] === id)
          ? (p as Row[]).map((r) => (r[idKey] === id ? { ...r, ...changes } : r))
          : p
        : pageOps.patch(p, id, changes, idKey),
    );
  },
  /** Replace the row `id` by the server's `row` wherever it sits. */
  replace<D>(data: D | undefined, id: string | number, row: object, idKey = 'id'): D | undefined {
    return mapPages(data, (p) =>
      Array.isArray(p)
        ? (p as Row[]).some((r) => r[idKey] === id)
          ? (p as Row[]).map((r) => (r[idKey] === id ? (row as Row) : r))
          : p
        : pageOps.replace(p, id, row, idKey),
    );
  },
  /** Drop the row `id` from whichever page holds it (an envelope's total moves with it). */
  remove<D>(data: D | undefined, id: string | number, idKey = 'id'): D | undefined {
    return mapPages(data, (p) =>
      Array.isArray(p)
        ? (p as Row[]).some((r) => r[idKey] === id)
          ? (p as Row[]).filter((r) => r[idKey] !== id)
          : p
        : pageOps.remove(p, id, idKey),
    );
  },
  /**
   * Put a NEW row first on the FIRST page (newest-first feeds). A row already on any page is replaced in
   * place instead (never duplicated). Other pages are left alone — they shift server-side and converge on settle.
   */
  prepend<D>(data: D | undefined, row: object, idKey = 'id'): D | undefined {
    if (!isInfinite(data) || data.pages.length === 0) return data;
    const id = (row as Row)[idKey] as string | number;
    const exists = data.pages.some((p) =>
      Array.isArray(p) ? (p as Row[]).some((r) => r[idKey] === id) : pageOps.patch(p, id, {}, idKey) !== p,
    );
    if (exists) return infiniteOps.replace(data, id, row, idKey);
    return mapPages(data, (p, i) => (i !== 0 ? p : Array.isArray(p) ? [row, ...p] : pageOps.add(p, row, 'prepend', idKey)));
  },
};
