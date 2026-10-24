/**
 * `jobPolling` — the ONE way to poll an async job's progress with TanStack Query.
 *
 * Why it exists (2026-10-13, Social Wiring CoreStudio): the "Gerar headlines"
 * modal froze at "estrutura 3 de 5" and the roteiro modal at "Preparando as
 * perguntas…" while the server had already finished. The hooks polled with a
 * bare `refetchInterval`, and TanStack PAUSES `refetchInterval` while
 * `document.visibilityState === 'hidden'` (`refetchIntervalInBackground`
 * defaults to `false`). The owner kicks off a 30 s job, switches tabs, comes
 * back — and the UI shows the progress it had when they left. The seed
 * QueryClient also sets `refetchOnWindowFocus: false`, so returning to the tab
 * did not catch up either. The progress UI lied about a job that was done.
 *
 * Spread it into `useQuery` in place of a hand-written `refetchInterval`:
 *
 * ```ts
 * useQuery({
 *   queryKey, queryFn,
 *   ...jobPolling((d: Lote | undefined) => !!d && emAndamento(d.status), POLL_MS),
 * });
 * ```
 *
 * Annotate the predicate's parameter with the query's EXACT data type (what
 * `queryFn` returns): the spread options are an inference site for `useQuery`'s
 * data type, so a narrower annotation (`{ items }` for `{ items; total }`)
 * narrows `data` for every consumer of the hook.
 *
 * While `isActive(data)` is true:
 *   - `refetchInterval` = `intervalMs`;
 *   - the interval keeps running in a background tab (`refetchIntervalInBackground`);
 *   - returning to the tab (`visibilitychange` → visible, which is TanStack's
 *     focus signal) refetches IMMEDIATELY (`refetchOnWindowFocus: 'always'`),
 *     because browsers throttle hidden-tab timers (Chrome: ≥1 min after 5 min
 *     hidden), so the last background tick can be far behind.
 * While it is false, the query does not poll at all — foreground or background —
 * and does not refetch on focus (the seed `createQueryClient` default). `refetchIntervalInBackground`
 * is a plain boolean in TanStack v5 (no per-state callback), so it is set to
 * `true` unconditionally; it has no effect when `refetchInterval` resolves to
 * `false`, which is what makes "background polling only while active" hold by
 * construction. An idle query never touches the network in the background.
 *
 * Not for "live" data with no terminal state (an inbox, a feed): that is a
 * realtime stream (`useRealtimeStream`), never a background poll.
 *
 * ## Starting a job: hand off with `handOffToPolling`
 *
 * `isActive(data)` only sees what the LAST read returned. A write that queues
 * server-side work (the answer is a job / consulta id, a 202, "queued") and then
 * invalidates the read races the worker: the refetch can land BEFORE the job's
 * rows exist, `isActive` is false, and the poll never starts — the screen keeps
 * saying nothing is happening (social-wiring F87, 2026-10-24: "Solicitar emissão"
 * and the certidões grid never moved until a reload). So a job-starting write
 * calls `handOffToPolling(qc, readKey)` instead of a bare invalidate: every
 * `jobPolling` read under `readKey` (prefix match) keeps polling until it has
 * SEEN the job active and then settled — or until `graceMs` passes.
 * `until: 'changed'` is for reads that carry no in-progress marker (the job's
 * effect is just "a row appears"): the hand-off ends at the first read whose
 * data differs from what was cached at hand-off time.
 * Keeper `check_job_start_without_handoff` gates the write side.
 * → KB § PATTERNS/frontend/frontend.md ("Job-progress polling")
 * → KB § PATTERNS/frontend/mutation-cache-writes.md ("Async jobs hand off")
 */
import { hashKey, partialMatchKey, type QueryKey } from '@tanstack/react-query';

/** The slice of a TanStack `Query` the callbacks read — kept structural so it fits any query type. */
export interface JobPollingQuery<TData> {
  state: { data: TData | undefined };
  /** Present on a real `Query`; what a pending `handOffToPolling` is matched against. */
  queryKey?: QueryKey;
  queryHash?: string;
}

export interface JobPollingOptions<TData> {
  refetchInterval: (query: JobPollingQuery<TData>) => number | false;
  refetchIntervalInBackground: true;
  refetchOnWindowFocus: (query: JobPollingQuery<TData>) => 'always' | false;
}

/**
 * Query options that poll every `intervalMs` while `isActive(data)` is true —
 * including while the tab is hidden — and refetch at once when the tab becomes
 * visible again. Idle (`isActive` false) ⇒ no polling at all.
 */
export function jobPolling<TData>(
  isActive: (data: TData | undefined) => boolean,
  intervalMs: number,
): JobPollingOptions<TData> {
  if (!Number.isFinite(intervalMs) || intervalMs <= 0) {
    throw new Error(`jobPolling: intervalMs must be a positive number, got ${intervalMs}`);
  }
  const polling = (query: JobPollingQuery<TData>) => {
    const active = isActive(query.state.data);
    return handOffPending(query, active) || active;
  };
  return {
    refetchInterval: (query) => (polling(query) ? intervalMs : false),
    refetchIntervalInBackground: true,
    refetchOnWindowFocus: (query) => (polling(query) ? 'always' : false),
  };
}

// ─── hand-off: a job-starting write → the polled read ──────────────────────

/** How long a hand-off keeps a read polling when it never sees the job (the safety net). */
export const JOB_HANDOFF_GRACE_MS = 90_000;

export interface HandOffToPollingOptions {
  /** Upper bound on the hand-off. Default `JOB_HANDOFF_GRACE_MS`. */
  graceMs?: number;
  /**
   * When the hand-off ends for a read: `'idle-after-active'` (default) — once `isActive` was
   * seen true and is false again; `'changed'` — at the first read whose data is not the data
   * cached at hand-off time (for reads with no in-progress marker); a function
   * `(data, before) => boolean` — once it says the job's effect landed (e.g. a row's
   * `ultima_sync_em` moved). All also end at `graceMs`.
   */
  until?: HandOffUntil;
  /** Clock seam for tests. */
  now?: () => number;
}

export type HandOffUntil =
  | 'idle-after-active'
  | 'changed'
  | ((data: unknown, before: unknown) => boolean);

interface HandOff {
  key: QueryKey;
  deadline: number;
  until: HandOffUntil;
  now: () => number;
  /** Data cached under each matching query at hand-off time (`'changed'` compares against it). */
  before: Map<string, unknown>;
  sawActive: Set<string>;
  done: Set<string>;
}

const handOffs = new Map<string, HandOff>();

function handOffPending<TData>(query: JobPollingQuery<TData>, active: boolean): boolean {
  if (!query.queryKey || handOffs.size === 0) return false;
  const hash = query.queryHash ?? hashKey(query.queryKey);
  let pending = false;
  for (const [id, h] of handOffs) {
    if (h.now() >= h.deadline) {
      handOffs.delete(id);
      continue;
    }
    if (h.done.has(hash) || !partialMatchKey(query.queryKey, h.key)) continue;
    if (active) {
      h.sawActive.add(hash);
      pending = true;
      continue;
    }
    const settled =
      typeof h.until === 'function'
        ? h.until(query.state.data, h.before.get(hash))
        : h.until === 'changed'
          ? h.before.has(hash) && h.before.get(hash) !== query.state.data
          : h.sawActive.has(hash);
    if (settled) {
      h.done.add(hash);
      continue;
    }
    pending = true;
  }
  return pending;
}

/**
 * The slice of a `QueryClient` a hand-off uses — structural, so a product whose own
 * `@tanstack/query-core` copy is a different module instance still type-checks.
 */
export interface HandOffQueryClient {
  getQueryCache(): { findAll(filters: { queryKey: QueryKey }): Array<{ queryHash: string; state: { data: unknown } }> };
  invalidateQueries(filters: { queryKey: QueryKey }): Promise<void>;
}

/**
 * Hand a job-starting write over to the `jobPolling` reads under `queryKey` (prefix match):
 * invalidate them now, and keep them polling until each has seen the job run and settle (or
 * changed, with `until: 'changed'`), or `graceMs` passes. Returns the invalidation promise.
 *
 * ```ts
 * onSuccess: () => handOffToPolling(qc, certidoesPartesKey(clienteId)),
 * ```
 *
 * Only reads that spread `jobPolling(...)` take part — a hand-off to a read that never polls is
 * just an invalidate. For a read with no in-progress marker, spread
 * `jobPolling(() => false, POLL_MS)`: it polls ONLY while a hand-off is pending.
 */
export function handOffToPolling(
  qc: HandOffQueryClient,
  queryKey: QueryKey,
  options: HandOffToPollingOptions = {},
): Promise<void> {
  const now = options.now ?? Date.now;
  const before = new Map<string, unknown>();
  for (const q of qc.getQueryCache().findAll({ queryKey })) before.set(q.queryHash, q.state.data);
  handOffs.set(hashKey(queryKey), {
    key: queryKey,
    deadline: now() + (options.graceMs ?? JOB_HANDOFF_GRACE_MS),
    until: options.until ?? 'idle-after-active',
    now,
    before,
    sawActive: new Set(),
    done: new Set(),
  });
  return qc.invalidateQueries({ queryKey });
}

/** Test seam: forget every pending hand-off. */
export function resetJobHandOffs(): void {
  handOffs.clear();
}
