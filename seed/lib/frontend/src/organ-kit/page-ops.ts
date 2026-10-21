/**
 * `pageOps` — pure edits for the paginated list envelopes the organs return: `{ data: T[], pagination: { total } }`
 * (items, inventory, purchasing, quotes, commerce) and `{ items: T[], total }` (photo-editing, guides, rules).
 * The `listOps` of `cache-writes` address a bare array; these address the rows inside the page and keep the total
 * honest.
 *
 * Same rules as `listOps`: an uncached entry (`undefined`) and anything that is not a page (a detail object, a bare
 * array) come back unchanged, so a `match: 'prefix'` target can safely reach every cached page / filter combination
 * plus the detail entries that share the prefix.
 *
 * Editing a row that is ALREADY on a page is safe anywhere (`patch` / `replace` / `remove`). A brand-new row is only
 * placed by `prependNewest`, for lists the server sorts newest-first: it goes on page 1 (other pages shift, so they
 * converge on the background settle). Any other placement (sort position, filters) is the server's call.
 *
 * KB § PATTERNS/frontend/mutation-cache-writes.md
 */
type Row = Record<string, unknown>;
/** A row's id: the name of the field holding it (default `id`) or a function for nested ids (`row => row.empresa.id`). */
export type IdKey = string | ((row: any) => unknown); // eslint-disable-line @typescript-eslint/no-explicit-any
/** Read a row's id through an `IdKey`. */
export const idOf = (row: unknown, idKey: IdKey): unknown => (typeof idKey === 'function' ? idKey(row) : (row as Row)[idKey]);
type PageLike = { data?: unknown; items?: unknown; itens?: unknown; total?: unknown; pagination?: Record<string, unknown> } & Row;

/** Which property holds the rows (`data` or `items`), or null when `v` is not a page. */
function rowsKey(v: unknown): 'data' | 'items' | 'itens' | null {
  if (!v || typeof v !== 'object' || Array.isArray(v)) return null;
  const p = v as PageLike;
  if (Array.isArray(p.data)) return 'data';
  if (Array.isArray(p.items)) return 'items';
  if (Array.isArray(p.itens)) return 'itens';
  return null;
}

const rowsOf = (page: PageLike, key: 'data' | 'items' | 'itens') => page[key] as Row[];

/** `page` with its rows replaced and its total moved by `delta` (wherever the envelope keeps it). */
function withRows<P>(page: P, key: 'data' | 'items' | 'itens', rows: Row[], delta = 0): P {
  const p = page as unknown as PageLike;
  const next: PageLike = { ...p, [key]: rows };
  if (delta !== 0) {
    if (p.pagination && typeof p.pagination.total === 'number') next.pagination = { ...p.pagination, total: Math.max(0, p.pagination.total + delta) };
    else if (typeof p.total === 'number') next.total = Math.max(0, p.total + delta);
  }
  return next as unknown as P;
}

const has = (rows: Row[], id: unknown, idKey: IdKey) => rows.some((r) => idOf(r, idKey) === id);

/** `page` with only its total moved by `delta` (wherever the envelope keeps it); rows untouched. Non-pages and total-less pages come back as-is. */
export function withTotal<P>(page: P, delta: number): P {
  const key = rowsKey(page);
  if (!key || delta === 0) return page;
  const p = page as unknown as PageLike;
  if (p.pagination && typeof p.pagination.total === 'number') return { ...p, pagination: { ...p.pagination, total: Math.max(0, p.pagination.total + delta) } } as unknown as P;
  if (typeof p.total === 'number') return { ...p, total: Math.max(0, p.total + delta) } as unknown as P;
  return page;
}

export const pageOps = {
  /** Merge `changes` into the row with `id` on this page (no-op when the row is not on it). */
  patch<P>(page: P | undefined, id: string | number, changes: object, idKey: IdKey = 'id'): P | undefined {
    const key = rowsKey(page);
    if (!key) return page;
    const rows = rowsOf(page as PageLike, key);
    if (!has(rows, id, idKey)) return page;
    return withRows(page, key, rows.map((r) => (idOf(r, idKey) === id ? { ...r, ...changes } : r)));
  },
  /** Swap the row with `id` for `row` (the server's version); no-op when absent. */
  replace<P>(page: P | undefined, id: string | number, row: object, idKey: IdKey = 'id'): P | undefined {
    const key = rowsKey(page);
    if (!key) return page;
    const rows = rowsOf(page as PageLike, key);
    if (!has(rows, id, idKey)) return page;
    return withRows(page, key, rows.map((r) => (idOf(r, idKey) === id ? (row as Row) : r)));
  },
  /** Drop the row with `id` and take one off the total; no-op when absent. */
  remove<P>(page: P | undefined, id: string | number, idKey: IdKey = 'id'): P | undefined {
    const key = rowsKey(page);
    if (!key) return page;
    const rows = rowsOf(page as PageLike, key);
    if (!has(rows, id, idKey)) return page;
    return withRows(page, key, rows.filter((r) => idOf(r, idKey) !== id), -1);
  },
  /**
   * Add a NEW row to the rows of a page (end or start) and one to the total; a row already there is left
   * alone (a refetch may have won the race). For small, unpaginated envelopes (`{ itens, total }`) where the
   * row certainly belongs; for paginated newest-first lists use `prependNewest`.
   */
  add<P>(page: P | undefined, row: object, where: 'append' | 'prepend' = 'append', idKey: IdKey = 'id'): P | undefined {
    const key = rowsKey(page);
    if (!key) return page;
    const rows = rowsOf(page as PageLike, key);
    if (has(rows, idOf(row, idKey), idKey)) return page;
    return withRows(page, key, where === 'prepend' ? [row as Row, ...rows] : [...rows, row as Row], 1);
  },
  /**
   * Put a row where the server's sort would put it on THIS page (before the first row that sorts after it,
   * `compare(row, r) < 0`; at the end when none does) and add one to the total. A row already on the page is
   * replaced (moved to its sorted place) and the total stays. For lists sorted by something other than recency
   * (name, due date) when the row certainly belongs on this page; pass the SAME comparator the server sorts by.
   */
  insertSorted<P>(page: P | undefined, row: object, compare: (a: any, b: any) => number, idKey: IdKey = 'id'): P | undefined { // eslint-disable-line @typescript-eslint/no-explicit-any
    const key = rowsKey(page);
    if (!key) return page;
    const rows = rowsOf(page as PageLike, key);
    const id = idOf(row, idKey);
    const existed = has(rows, id, idKey);
    const rest = rows.filter((r) => idOf(r, idKey) !== id);
    const at = rest.findIndex((r) => compare(row, r) < 0);
    const next = at === -1 ? [...rest, row as Row] : [...rest.slice(0, at), row as Row, ...rest.slice(at)];
    return withRows(page, key, next, existed ? 0 : 1);
  },
  /**
   * Put a NEW row first on page 1 of a newest-first list (and add one to the total, trimming to `page_size`).
   * Pages other than the first are left alone — they shift server-side and converge on the settle. A row already
   * on the page is replaced in place instead (never duplicated).
   *
   * "Page 1" is read from `page.page` or `page.pagination.page`; an envelope with NEITHER field is
   * ASSUMED to be page 1 (the unpaginated / first-page-only case) — so do not point this at a cache
   * entry that is a later page without a page number.
   */
  prependNewest<P>(page: P | undefined, row: object, idKey: IdKey = 'id'): P | undefined {
    const key = rowsKey(page);
    if (!key) return page;
    const p = page as PageLike;
    const rows = rowsOf(p, key);
    const id = idOf(row, idKey);
    if (has(rows, id, idKey)) return pageOps.replace(page, id as string | number, row, idKey);
    const no = typeof p.page === 'number' ? p.page : typeof p.pagination?.page === 'number' ? p.pagination.page : 1;
    if (no !== 1) return page;
    const size = typeof p.page_size === 'number' ? p.page_size : typeof p.pagination?.page_size === 'number' ? p.pagination.page_size : rows.length + 1;
    return withRows(page, key, [row as Row, ...rows].slice(0, Math.max(size, 1)), 1);
  },
};
