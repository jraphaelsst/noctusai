/**
 * Cache edits for the organs' list envelopes — the sibling of `listOps` (cache-writes.ts) for the
 * `{ data: T[], pagination }` shape every staff organ list (parties, contracts, finance entries,
 * statements, reminder log) answers with, plus the `{ data: T[] }` roster shape.
 *
 * Same tolerance as `listOps`: an uncached entry (`undefined`) and anything that is not an envelope
 * with a `data` array pass through unchanged, so a `match: 'prefix'` target never mangles a detail
 * object that shares the prefix.
 *
 * Deliberately NOT here: inserting a created row. Whether it belongs on page N of a filtered list is
 * the server's call, so creates commit the row into its DETAIL key and let the settle refetch place it
 * in the lists.
 *
 * KB § PATTERNS/frontend/mutation-cache-writes.md
 */
import { listOps } from '../cache-writes';

export interface DataEnvelope<T> {
  data: T[];
  pagination?: { total?: number; [k: string]: unknown };
}

function isEnvelope<T>(page: unknown): page is DataEnvelope<T> {
  return !!page && typeof page === 'object' && !Array.isArray(page) && Array.isArray((page as DataEnvelope<T>).data);
}

export const envelopeOps = {
  /** Merge `changes` into the row `id` wherever it is on the page. */
  patch<T extends { id: string }>(page: DataEnvelope<T> | undefined, id: string, changes: Partial<NoInfer<T>>): DataEnvelope<T> | undefined {
    if (!isEnvelope<T>(page)) return page;
    if (!page.data.some((r) => r.id === id)) return page;
    return { ...page, data: listOps.patch(page.data, id, changes) as T[] };
  },
  /** Drop the row `id` from the page (and the page's `total`, when it carries one). */
  remove<T extends { id: string }>(page: DataEnvelope<T> | undefined, id: string): DataEnvelope<T> | undefined {
    if (!isEnvelope<T>(page)) return page;
    if (!page.data.some((r) => r.id === id)) return page;
    const total = page.pagination?.total;
    return {
      ...page,
      data: page.data.filter((r) => r.id !== id),
      ...(page.pagination && typeof total === 'number'
        ? { pagination: { ...page.pagination, total: Math.max(0, total - 1) } }
        : {}),
    };
  },
};
