/**
 * cache-writes — a mutation puts what it knows into the cache, it does not
 * just ask the server again.
 *
 * The shape this replaces (94% of the fleet's mutations on 2026-10-21):
 *
 *     onSuccess: () => qc.invalidateQueries({ queryKey: listKey })
 *
 * The server already answered the POST with the row it created, and the
 * hook throws that answer away and fetches the whole list again. What the
 * user sees changing is therefore TWO round trips late (write + refetch —
 * ~1-3 s on prod), and for that whole time the screen says the write did
 * not happen. Found live on orbity's lead notes: the toast said "Atividade
 * registrada" while the list underneath still said "Nenhuma atividade".
 *
 * `useCacheWriteMutation` gives every write the same three-step contract:
 *
 * 1. **optimistic** (opt-in, per target) — the change is drawn the instant
 *    the user acts; the target's previous value is snapshotted.
 * 2. **commit** (per target) — the SERVER's answer is written into the
 *    cache as soon as it arrives (replacing the optimistic stand-in), so the
 *    screen is correct after one round trip even without optimism.
 * 3. **settle** (never awaited — `isPending` ends at the commit, not after the refetch) — every target (plus `invalidate`) is invalidated in the
 *    background so derived/server-computed fields converge. The data on
 *    screen is already right; this refetch only refreshes it
 *    (`isFetching && !!data` — never a skeleton).
 *
 * On failure every optimistically-touched target is rolled back to its
 * snapshot, then settle re-reads the truth.
 *
 * A target without `optimistic` is only written on success; a target without
 * `commit` is only invalidated. Use `listOps` for the common list edits.
 *
 * KB § PATTERNS/frontend/mutation-cache-writes.md
 */
import {
  useMutation,
  useQueryClient,
  type QueryKey,
  type UseMutationOptions,
  type UseMutationResult,
} from '@tanstack/react-query';

/** Prefix of the stand-in id an optimistic row carries until the server answers. */
export const OPTIMISTIC_ID_PREFIX = 'optimistic:';

let optimisticCounter = 0;

/** A fresh, recognisable stand-in id for an optimistically-inserted row. */
export function optimisticId(): string {
  optimisticCounter += 1;
  return `${OPTIMISTIC_ID_PREFIX}${Date.now().toString(36)}-${optimisticCounter}`;
}

/** True while a row is the optimistic stand-in (no server id yet). */
export function isOptimistic(row: { id?: unknown } | null | undefined): boolean {
  return typeof row?.id === 'string' && row.id.startsWith(OPTIMISTIC_ID_PREFIX);
}

export interface CacheWriteContext {
  /** The stand-in id this mutation call minted (one per `mutate`). */
  tempId: string;
}

export interface CacheWriteTarget<TData, TVars, TCached = unknown> {
  queryKey: QueryKey;
  /**
   * `'exact'` (default) touches that one cache entry. `'prefix'` touches EVERY cached entry whose
   * key starts with `queryKey` — e.g. `[resource]` reaches each `[resource, filters]` list at once.
   * Under `'prefix'` the edit also sees non-list entries (a `[resource, id]` detail): `listOps`
   * pass anything that is not an array through untouched, so list edits stay safe there.
   */
  match?: 'exact' | 'prefix';
  /**
   * Under `match: 'prefix'`, pick WHICH matched entries this target touches (e.g. only the list whose
   * key carries the same account / scope as the row being written). Entries it rejects are neither
   * edited nor snapshotted; settle still invalidates the whole prefix. Ignored for `'exact'`.
   */
  predicate?: (queryKey: QueryKey) => boolean;
  /** Draw the change before the server answers. `old` is undefined when the query is not cached. */
  optimistic?: (old: TCached | undefined, vars: TVars, ctx: CacheWriteContext, queryKey?: QueryKey) => TCached | undefined;
  /** Write the server's answer. Runs on the value currently cached (which may hold the optimistic stand-in). */
  commit?: (old: TCached | undefined, result: TData, vars: TVars, ctx: CacheWriteContext, queryKey?: QueryKey) => TCached | undefined;
}

type Snapshot = { queryKey: QueryKey; previous: unknown };

export interface CacheWriteMutationContext extends CacheWriteContext {
  snapshots: Snapshot[];
}

export interface UseCacheWriteMutationOptions<TData, TVars>
  extends Omit<
    UseMutationOptions<TData, Error, TVars, CacheWriteMutationContext>,
    'mutationFn' | 'onMutate' | 'onSettled'
  > {
  mutationFn: (vars: TVars) => Promise<TData>;
  /** Cache entries this write updates. A function receives the call's vars (per-entity keys). */
  targets:
    | CacheWriteTarget<TData, TVars, any>[]
    | ((vars: TVars) => CacheWriteTarget<TData, TVars, any>[]);
  /** Extra keys refreshed in the background after the write settles (derived views: counts, funnels...). */
  invalidate?: QueryKey[] | ((vars: TVars) => QueryKey[]);
}

/**
 * `useMutation` with the optimistic → commit → settle contract described in
 * the module docstring. `onSuccess` / `onError` from the caller still run
 * (after the cache work), so toasts and form resets stay where they are.
 */
export function useCacheWriteMutation<TData, TVars>(
  options: UseCacheWriteMutationOptions<TData, TVars>,
): UseMutationResult<TData, Error, TVars, CacheWriteMutationContext> {
  const qc = useQueryClient();
  const { targets, invalidate, onSuccess, onError, ...rest } = options;
  const resolveTargets = (vars: TVars) => (typeof targets === 'function' ? targets(vars) : targets);
  /** The cached keys a target addresses right now (prefix → every matching entry that is cached). */
  const keysOf = (t: CacheWriteTarget<TData, TVars, any>): QueryKey[] =>
    t.match === 'prefix'
      ? qc.getQueriesData({ queryKey: t.queryKey }).map(([key]) => key).filter((key) => !t.predicate || t.predicate(key))
      : [t.queryKey];
  const resolveInvalidate = (vars: TVars) =>
    (typeof invalidate === 'function' ? invalidate(vars) : invalidate) ?? [];

  return useMutation<TData, Error, TVars, CacheWriteMutationContext>({
    ...rest,
    onMutate: async (vars) => {
      const ctx: CacheWriteMutationContext = { tempId: optimisticId(), snapshots: [] };
      const optimisticTargets = resolveTargets(vars).filter((t) => t.optimistic);
      // An in-flight refetch landing after the optimistic write would erase it.
      await Promise.all(optimisticTargets.map((t) => qc.cancelQueries({ queryKey: t.queryKey })));
      for (const t of optimisticTargets) {
        for (const queryKey of keysOf(t)) {
          const previous = qc.getQueryData(queryKey);
          const next = t.optimistic!(previous, vars, ctx, queryKey);
          if (next === undefined || next === previous) continue;
          ctx.snapshots.push({ queryKey, previous });
          qc.setQueryData(queryKey, next);
        }
      }
      return ctx;
    },
    onSuccess: (result, vars, ctx, mutationCtx) => {
      for (const t of resolveTargets(vars)) {
        if (!t.commit) continue;
        for (const queryKey of keysOf(t)) {
          const old = qc.getQueryData(queryKey);
          const next = t.commit(old, result, vars, ctx, queryKey);
          if (next !== undefined && next !== old) qc.setQueryData(queryKey, next);
        }
      }
      return onSuccess?.(result, vars, ctx, mutationCtx);
    },
    onError: (error, vars, ctx, mutationCtx) => {
      for (const s of ctx?.snapshots ?? []) qc.setQueryData(s.queryKey, s.previous);
      return onError?.(error, vars, ctx, mutationCtx);
    },
    onSettled: (_data, _error, vars) => {
      const keys = [...resolveTargets(vars).map((t) => t.queryKey), ...resolveInvalidate(vars)];
      // Fire and forget: TanStack awaits whatever onSettled returns before leaving `isPending`, so
      // returning this promise would hold every "Adicionando…" button until the refetches finish.
      // invalidateQueries does not reject (a failed refetch lands in the query's own error state
      // unless `throwOnError` is set, which we never do), so there is nothing to swallow.
      void Promise.all(keys.map((queryKey) => qc.invalidateQueries({ queryKey })));
    },
  });
}

/** Row ids are strings or numbers (Mailchimp segments, serial keys). */
export type RowId = string | number;
type AnyRow = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

/**
 * Pure list edits for `optimistic` / `commit`. Every op tolerates an
 * uncached list (`undefined` in → `undefined` out = "leave it uncached"), and
 * returns anything that is not an array unchanged — so a `match: 'prefix'`
 * target never mangles a detail object or a paginated `{ items }` envelope
 * that shares the prefix (settle's refetch converges those).
 *
 * Rows are addressed by `id` unless the trailing `idKey` says otherwise
 * (`hostname`, `slug`, …); ids may be strings or numbers.
 */
export const listOps = {
  append<T>(list: T[] | undefined, item: T): T[] | undefined {
    if (!Array.isArray(list)) return list;
    return [...list, item];
  },
  prepend<T>(list: T[] | undefined, item: T): T[] | undefined {
    if (!Array.isArray(list)) return list;
    return [item, ...list];
  },
  /**
   * Insert `item` where the server's sort would put it: before the first row that sorts after it
   * (`compare(item, row) < 0`), after equal rows; at the end when none does. A row already present
   * (same `idKey`) is replaced in place instead — never duplicated. Pass the SAME comparator the
   * server sorts by (e.g. `(a, b) => a.name.localeCompare(b.name)`); never re-sort in a component.
   */
  insertSorted<T extends AnyRow>(list: T[] | undefined, item: T, compare: (a: T, b: T) => number, idKey = 'id'): T[] | undefined {
    if (!Array.isArray(list)) return list;
    const rest = list.filter((r) => r[idKey] !== item[idKey]);
    const at = rest.findIndex((r) => compare(item, r) < 0);
    return at === -1 ? [...rest, item] : [...rest.slice(0, at), item, ...rest.slice(at)];
  },
  /** Replace the row with `matchId` (the stand-in or the real id) by `item`; append when absent. */
  replace<T extends AnyRow>(list: T[] | undefined, matchId: RowId, item: T, where: 'append' | 'prepend' = 'append', idKey = 'id'): T[] | undefined {
    if (!Array.isArray(list)) return list;
    // The server row may already be there (a background refetch won the race) — never duplicate it.
    const hit = (r: T) => r[idKey] === matchId || r[idKey] === item[idKey];
    const rest = list.filter((r) => !hit(r));
    const at = list.findIndex(hit);
    if (at === -1) return where === 'prepend' ? [item, ...rest] : [...rest, item];
    const out = [...rest];
    out.splice(Math.min(at, out.length), 0, item);
    return out;
  },
  patch<T extends AnyRow>(list: T[] | undefined, id: RowId, changes: Partial<NoInfer<T>>, idKey = 'id'): T[] | undefined {
    if (!Array.isArray(list)) return list;
    return list.map((r) => (r[idKey] === id ? { ...r, ...changes } : r));
  },
  /**
   * Replace the row `id` by `fn(row)` — for edits `patch` cannot express, chiefly a NESTED edit (a row
   * inside a row): `listOps.update(leads, leadId, (l) => ({ ...l, activities: listOps.prepend(l.activities, a) }))`.
   * Inside an envelope: `listOps.within(old, 'items', (l) => listOps.update(l, id, fn))`. Absent row → unchanged.
   */
  update<T extends AnyRow>(list: T[] | undefined, id: RowId, fn: (row: T) => T, idKey = 'id'): T[] | undefined {
    if (!Array.isArray(list)) return list;
    return list.map((r) => (r[idKey] === id ? fn(r) : r));
  },
  /** Merge `changes` into a single cached entity (a detail query); non-objects pass through. */
  merge<T extends object>(entity: T | undefined, changes: Partial<NoInfer<T>>): T | undefined {
    if (!entity || typeof entity !== 'object' || Array.isArray(entity)) return entity;
    return { ...entity, ...changes };
  },
  remove<T extends AnyRow>(list: T[] | undefined, id: RowId, idKey = 'id'): T[] | undefined {
    if (!Array.isArray(list)) return list;
    return list.filter((r) => r[idKey] !== id);
  },
  /**
   * Apply a list edit to the array an envelope keeps under `field` — for responses shaped
   * `{ items: [...] }`, `{ itens: [...] }`, `{ colecoes: [...] }`, … Composes with the ops above:
   * `listOps.within(old, 'items', (l) => listOps.remove(l, id))`. An uncached entry or one with
   * no array at `field` passes through unchanged (safe under `match: 'prefix'`). For paginated
   * envelopes whose TOTAL must move with the rows (`{data, pagination}` / `{items, total}`),
   * use `pageOps` (re-exported below).
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  within<E extends object>(env: E | undefined, field: keyof E & string, fn: (list: any[]) => any[] | undefined): E | undefined {
    if (!env || typeof env !== 'object') return env;
    const list = (env as Record<string, unknown>)[field];
    if (!Array.isArray(list)) return env;
    const next = fn(list);
    return next ? { ...env, [field]: next } : env;
  },
};

/** Paginated-envelope edits (rows + total). One home for every cache edit: import from `cache-writes`. */
export { pageOps } from './organ-kit/page-ops';
/** Infinite-query (`{ pages, pageParams }`) edits. */
export { infiniteOps } from './organ-kit/infinite-ops';
/** Row / board edits for list-or-envelope-or-detail caches + the target builders built on them. */
export { rowOps, boardOps, patchById, removeById, addTo } from './organ-kit/row-ops';
