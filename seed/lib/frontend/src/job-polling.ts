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
 * → KB § PATTERNS/frontend/frontend.md ("Job-progress polling")
 */

/** The slice of a TanStack `Query` the callbacks read — kept structural so it fits any query type. */
export interface JobPollingQuery<TData> {
  state: { data: TData | undefined };
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
  return {
    refetchInterval: (query) => (isActive(query.state.data) ? intervalMs : false),
    refetchIntervalInBackground: true,
    refetchOnWindowFocus: (query) => (isActive(query.state.data) ? 'always' : false),
  };
}
