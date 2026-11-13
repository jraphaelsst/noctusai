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
 *   - `refetchInterval` = `intervalMs` while the tab is visible; a HIDDEN tab pauses (nobody is
 *     watching — request budget, 2026-11-10; `refetchIntervalInBackground` is false);
 *   - returning to the tab (`visibilitychange` → visible, TanStack's focus signal) refetches
 *     IMMEDIATELY (`refetchOnWindowFocus: 'always'`) — that catch-up is what fixes the 2026-10-13 freeze;
 *   - after 2 min the cadence slows to 15 s; after 30 min of VISIBLE polling it STOPS and
 *     `useJobPollingStalled()` turns true — the shell's `JobPollingPausedNotice` says so in pt-BR with an
 *     "Atualizar" button (`resumeJobPolling`). Never a silently stale screen.
 * While it is false, the query does not poll at all and does not refetch on focus.
 *
 * A job with a progress stream (`useJobProgress`, `noctusai_lib.realtime.job_progress`) is PUSHED, not polled:
 * while its stream is open this read does not poll; if the stream cannot be kept the hook falls back to
 * `handOffToPolling` and this polling takes over again.
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
import { useSyncExternalStore } from 'react';
import { hashKey, partialMatchKey, type QueryClient, type QueryKey } from '@tanstack/react-query';

/** The slice of a TanStack `Query` the callbacks read — kept structural so it fits any query type. */
export interface JobPollingQuery<TData> {
  state: { data: TData | undefined };
  /** Present on a real `Query`; what a pending `handOffToPolling` is matched against. */
  queryKey?: QueryKey;
  queryHash?: string;
  getObserversCount?: () => number;
}

export interface JobPollingOptions<TData> {
  refetchInterval: (query: JobPollingQuery<TData>) => number | false;
  refetchIntervalInBackground: false;
  refetchOnWindowFocus: (query: JobPollingQuery<TData>) => 'always' | false;
}

/**
 * Query options that poll every `intervalMs` while `isActive(data)` is true and the tab is
 * visible (a hidden tab pauses; there is no `refetchIntervalInBackground`), and refetch at once when the tab becomes
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
  // Request budget (2026-11-10): "active" is the SERVER's claim; a job stuck active is an endless per-tick
  // Supabase spend. Back off after the fast window, stop at the ceiling — and SAY so (stalled notice).
  const cadence = (query: JobPollingQuery<TData>): number | false => {
    if (!polling(query)) {
      clearBudget(query);
      return false;
    }
    // A live job-progress stream (`useJobProgress`) is pushing this read's updates: do not ALSO poll it.
    if (streamCovers(query)) return false;
    const elapsed = visibleActiveMs(query);
    if (elapsed >= JOB_POLL_CEILING_MS) {
      markStalled(query);
      return false;
    }
    return elapsed >= JOB_POLL_FAST_WINDOW_MS ? Math.max(intervalMs, JOB_POLL_SLOW_MS) : intervalMs;
  };
  return {
    // poll-budget: caller-set 2-5s while a job is active, 15s after 2 min, stops at 30 min visible; ~5 calls/tick (handler + auth lookups); worst 760/day per open tab per stuck job (then stops and shows the notice); hidden=paused
    refetchInterval: (query) => cadence(query),
    // A hidden tab has nobody watching; `refetchOnWindowFocus: 'always'` catches up the moment it is visible.
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: (query) => (polling(query) ? 'always' : false),
  };
}

// ─── request budget: visible-active time + the "stalled" signal ───────────

/** A gap between two callbacks longer than this means the tab was hidden/asleep: not counted as watching time. */
const WATCH_GAP_MS = 60_000;
const budgets = new WeakMap<object, { last: number; visibleMs: number }>();
const stalled = new Set<JobPollingQuery<any>>();
const stalledListeners = new Set<() => void>();

function visibleActiveMs(query: JobPollingQuery<any>): number {
  const now = Date.now();
  const b = budgets.get(query) ?? { last: now, visibleMs: 0 };
  const delta = now - b.last;
  if (delta <= WATCH_GAP_MS) b.visibleMs += delta;
  b.last = now;
  budgets.set(query, b);
  return b.visibleMs;
}

function notifyStalled() {
  stalledListeners.forEach((l) => l());
}

function markStalled(query: JobPollingQuery<any>) {
  if (stalled.has(query)) return;
  stalled.add(query);
  notifyStalled();
}

function clearBudget(query: JobPollingQuery<any>) {
  budgets.delete(query);
  if (stalled.delete(query)) notifyStalled();
}

/** True while a watched job is still active on the server but its automatic refresh gave up (30 min). */
export function isJobPollingStalled(): boolean {
  for (const query of stalled) {
    if (query.getObserversCount && query.getObserversCount() === 0) stalled.delete(query);
  }
  return stalled.size > 0;
}

/** Subscribe to the stalled flag changing (what `useJobPollingStalled` is built on). */
export function subscribeJobPollingStalled(listener: () => void): () => void {
  stalledListeners.add(listener);
  return () => stalledListeners.delete(listener);
}

/** React hook: `true` while any watched job's automatic refresh is paused at the ceiling. */
export function useJobPollingStalled(): boolean {
  return useSyncExternalStore(subscribeJobPollingStalled, isJobPollingStalled, () => false);
}

/** "Atualizar": reset the stalled jobs' budget and refetch them, which starts polling again. */
export function resumeJobPolling(qc: Pick<QueryClient, 'invalidateQueries'>): void {
  const queries = [...stalled];
  queries.forEach((query) => {
    budgets.delete(query);
    stalled.delete(query);
  });
  notifyStalled();
  queries.forEach((query) => {
    if (query.queryKey) void qc.invalidateQueries({ queryKey: query.queryKey, exact: true });
  });
}

/** Test seam. */
export function resetJobPollingStalled(): void {
  stalled.clear();
  notifyStalled();
}

// ─── push: a live SSE stream replaces the poll ─────────────────────────────

const liveStreams = new Map<number, QueryKey>();
let liveStreamSeq = 0;

/**
 * Declare that a job-progress stream is live for the reads under `queryKey` (prefix match):
 * their `jobPolling` stops polling while it is. Returns the release function; releasing (stream
 * lost, finished, unmounted) hands the read straight back to polling. Used by `useJobProgress`.
 */
export function markJobStreamLive(queryKey: QueryKey): () => void {
  const id = ++liveStreamSeq;
  liveStreams.set(id, queryKey);
  return () => {
    liveStreams.delete(id);
  };
}

function streamCovers(query: JobPollingQuery<any>): boolean {
  if (!query.queryKey || liveStreams.size === 0) return false;
  for (const key of liveStreams.values()) if (partialMatchKey(query.queryKey, key)) return true;
  return false;
}

/** Test seam. */
export function resetJobStreams(): void {
  liveStreams.clear();
}

// ─── hand-off: a job-starting write → the polled read ──────────────────────

/** Fast cadence lasts this long, then `JOB_POLL_SLOW_MS`; polling stops at `JOB_POLL_CEILING_MS` of continuous "active". */
export const JOB_POLL_FAST_WINDOW_MS = 2 * 60_000;
export const JOB_POLL_SLOW_MS = 15_000;
export const JOB_POLL_CEILING_MS = 30 * 60_000;

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
