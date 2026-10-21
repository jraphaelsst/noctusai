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
type PageLike = { data?: unknown; items?: unknown; total?: unknown; pagination?: Record<string, unknown> } & Row;

/** Which property holds the rows (`data` or `items`), or null when `v` is not a page. */
function rowsKey(v: unknown): 'data' | 'items' | null {
  if (!v || typeof v !== 'object' || Array.isArray(v)) return null;
  const p = v as PageLike;
  if (Array.isArray(p.data)) return 'data';
  if (Array.isArray(p.items)) return 'items';
  return null;
}

const rowsOf = (page: PageLike, key: 'data' | 'items') => page[key] as Row[];

/** `page` with its rows replaced and its total moved by `delta` (wherever the envelope keeps it). */
function withRows<P>(page: P, key: 'data' | 'items', rows: Row[], delta = 0): P {
  const p = page as unknown as PageLike;
  const next: PageLike = { ...p, [key]: rows };
  if (delta !== 0) {
    if (p.pagination && typeof p.pagination.total === 'number') next.pagination = { ...p.pagination, total: Math.max(0, p.pagination.total + delta) };
    else if (typeof p.total === 'number') next.total = Math.max(0, p.total + delta);
  }
  return next as unknown as P;
}

const has = (rows: Row[], id: unknown, idKey: string) => rows.some((r) => r[idKey] === id);

export const pageOps = {
  /** Merge `changes` into the row with `id` on this page (no-op when the row is not on it). */
  patch<P>(page: P | undefined, id: string, changes: object, idKey = 'id'): P | undefined {
    const key = rowsKey(page);
    if (!key) return page;
    const rows = rowsOf(page as PageLike, key);
    if (!has(rows, id, idKey)) return page;
    return withRows(page, key, rows.map((r) => (r[idKey] === id ? { ...r, ...changes } : r)));
  },
  /** Swap the row with `id` for `row` (the server's version); no-op when absent. */
  replace<P>(page: P | undefined, id: string, row: object, idKey = 'id'): P | undefined {
    const key = rowsKey(page);
    if (!key) return page;
    const rows = rowsOf(page as PageLike, key);
    if (!has(rows, id, idKey)) return page;
    return withRows(page, key, rows.map((r) => (r[idKey] === id ? (row as Row) : r)));
  },
  /** Drop the row with `id` and take one off the total; no-op when absent. */
  remove<P>(page: P | undefined, id: string, idKey = 'id'): P | undefined {
    const key = rowsKey(page);
    if (!key) return page;
    const rows = rowsOf(page as PageLike, key);
    if (!has(rows, id, idKey)) return page;
    return withRows(page, key, rows.filter((r) => r[idKey] !== id), -1);
  },
  /**
   * Put a NEW row first on page 1 of a newest-first list (and add one to the total, trimming to `page_size`).
   * Pages other than the first are left alone — they shift server-side and converge on the settle. A row already
   * on the page is replaced in place instead (never duplicated).
   */
  prependNewest<P>(page: P | undefined, row: object, idKey = 'id'): P | undefined {
    const key = rowsKey(page);
    if (!key) return page;
    const p = page as PageLike;
    const rows = rowsOf(p, key);
    const id = (row as Row)[idKey];
    if (has(rows, id, idKey)) return pageOps.replace(page, id as string, row, idKey);
    const no = typeof p.page === 'number' ? p.page : typeof p.pagination?.page === 'number' ? p.pagination.page : 1;
    if (no !== 1) return page;
    const size = typeof p.page_size === 'number' ? p.page_size : typeof p.pagination?.page_size === 'number' ? p.pagination.page_size : rows.length + 1;
    return withRows(page, key, [row as Row, ...rows].slice(0, Math.max(size, 1)), 1);
  },
};
