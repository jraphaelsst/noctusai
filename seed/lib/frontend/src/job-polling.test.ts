/**
 * jobPolling — polls only while the job is active, keeps polling in a hidden
 * tab, and refetches at once when the tab becomes visible again.
 *
 * The integration cases drive a REAL QueryClient + QueryObserver and flip
 * TanStack's own `focusManager` (its public seam for "tab hidden/visible"),
 * so they exercise the exact gate that froze the CoreStudio modals.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryObserver, focusManager } from '@tanstack/react-query';

import { handOffToPolling, jobPolling, resetJobHandOffs, type JobPollingQuery } from './job-polling';

type Job = { status: 'processando' | 'concluido' };
const running = (d: Job | undefined) => d?.status === 'processando';
const q = (data: Job | undefined): JobPollingQuery<Job> => ({ state: { data } });

describe('jobPolling — options', () => {
  it('polls at the interval while active, and not at all while idle', () => {
    const o = jobPolling(running, 3000);
    expect(o.refetchInterval(q({ status: 'processando' }))).toBe(3000);
    expect(o.refetchInterval(q({ status: 'concluido' }))).toBe(false);
    expect(o.refetchInterval(q(undefined))).toBe(false);
  });

  it('enables background polling (a no-op while refetchInterval is false)', () => {
    expect(jobPolling(running, 3000).refetchIntervalInBackground).toBe(true);
  });

  it("refetches on return to the tab ('always') only while active", () => {
    const o = jobPolling(running, 3000);
    expect(o.refetchOnWindowFocus(q({ status: 'processando' }))).toBe('always');
    expect(o.refetchOnWindowFocus(q({ status: 'concluido' }))).toBe(false);
  });

  it('refuses a non-positive interval loudly', () => {
    expect(() => jobPolling(running, 0)).toThrow(/positive/);
    expect(() => jobPolling(running, Number.NaN)).toThrow(/positive/);
  });
});

describe('jobPolling — against a real QueryObserver', () => {
  let client: QueryClient;

  beforeEach(() => {
    vi.useFakeTimers();
    client = new QueryClient({
      // The seed client's default — the focus refetch must come from jobPolling.
      defaultOptions: { queries: { refetchOnWindowFocus: false, retry: false } },
    });
    client.mount(); // what QueryClientProvider does — subscribes to focusManager
  });

  afterEach(() => {
    client.unmount();
    client.clear();
    focusManager.setFocused(undefined);
    vi.useRealTimers();
  });

  function observe(statuses: Job['status'][]) {
    let calls = 0;
    const queryFn = vi.fn(async () => {
      const status = statuses[Math.min(calls, statuses.length - 1)];
      calls += 1;
      return { status } as Job;
    });
    const observer = new QueryObserver(client, {
      queryKey: ['job'],
      queryFn,
      ...jobPolling(running, 1000),
    });
    const unsubscribe = observer.subscribe(() => {});
    return { queryFn, unsubscribe };
  }

  it('keeps polling while the tab is hidden — the CoreStudio freeze', async () => {
    const { queryFn, unsubscribe } = observe(['processando']);
    await vi.advanceTimersByTimeAsync(0);
    expect(queryFn).toHaveBeenCalledTimes(1);

    focusManager.setFocused(false); // tab hidden
    await vi.advanceTimersByTimeAsync(3000);
    expect(queryFn).toHaveBeenCalledTimes(4);
    unsubscribe();
  });

  it('stops polling (hidden or not) once the job is done', async () => {
    const { queryFn, unsubscribe } = observe(['processando', 'concluido']);
    await vi.advanceTimersByTimeAsync(0);
    focusManager.setFocused(false);
    await vi.advanceTimersByTimeAsync(1000); // 2nd fetch → concluido
    expect(queryFn).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(5000);
    expect(queryFn).toHaveBeenCalledTimes(2);
    focusManager.setFocused(true); // back to the tab: idle ⇒ no focus refetch
    await vi.advanceTimersByTimeAsync(0);
    expect(queryFn).toHaveBeenCalledTimes(2);
    unsubscribe();
  });

  it('refetches immediately when the tab becomes visible while the job runs', async () => {
    const { queryFn, unsubscribe } = observe(['processando']);
    await vi.advanceTimersByTimeAsync(0);
    expect(queryFn).toHaveBeenCalledTimes(1);
    focusManager.setFocused(false);
    focusManager.setFocused(true); // visible again, before the next tick
    await vi.advanceTimersByTimeAsync(0);
    expect(queryFn).toHaveBeenCalledTimes(2);
    unsubscribe();
  });

  it('a bare refetchInterval (the old shape) does freeze in a hidden tab', async () => {
    let calls = 0;
    const observer = new QueryObserver(client, {
      queryKey: ['bare'],
      queryFn: async () => {
        calls += 1;
        return { status: 'processando' } as Job;
      },
      refetchInterval: 1000,
    });
    const unsubscribe = observer.subscribe(() => {});
    await vi.advanceTimersByTimeAsync(0);
    focusManager.setFocused(false);
    await vi.advanceTimersByTimeAsync(3000);
    expect(calls).toBe(1);
    unsubscribe();
  });
});

describe('handOffToPolling — a job-starting write hands off to the polled read (F87)', () => {
  let client: QueryClient;
  type Grid = { cells: Job['status'][] };
  const gridRunning = (d: Grid | undefined) => !!d && d.cells.includes('processando');

  beforeEach(() => {
    vi.useFakeTimers();
    resetJobHandOffs();
    client = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false, retry: false } } });
    client.mount();
  });

  afterEach(() => {
    client.unmount();
    client.clear();
    resetJobHandOffs();
    vi.useRealTimers();
  });

  /** A read whose server answers `answers[n]` on the n-th fetch (last one repeats). */
  function grid(answers: Grid[], key: readonly unknown[] = ['sw', 'c1', 'partes', null]) {
    let n = 0;
    const queryFn = vi.fn(async () => answers[Math.min(n++, answers.length - 1)]);
    const observer = new QueryObserver(client, { queryKey: key, queryFn, ...jobPolling(gridRunning, 1000) });
    const unsubscribe = observer.subscribe(() => {});
    return { queryFn, unsubscribe };
  }

  it('without a hand-off the poll never starts when the refetch beats the worker (the bug)', async () => {
    // fetch 1: idle grid · fetch 2 (the invalidate): the worker has not created the rows yet.
    const { queryFn, unsubscribe } = grid([{ cells: [] }, { cells: [] }, { cells: ['processando'] }]);
    await vi.advanceTimersByTimeAsync(0);
    await client.invalidateQueries({ queryKey: ['sw', 'c1'] });
    await vi.advanceTimersByTimeAsync(10_000);
    expect(queryFn).toHaveBeenCalledTimes(2); // stuck: the job runs, the screen never knows
    unsubscribe();
  });

  it('keeps polling through the race, follows the job, and stops once it settles', async () => {
    const { queryFn, unsubscribe } = grid([
      { cells: [] }, // mounted, idle
      { cells: [] }, // the hand-off refetch beats the worker
      { cells: [] },
      { cells: ['processando'] }, // the job is visible
      { cells: ['concluido'] }, // settled
    ]);
    await vi.advanceTimersByTimeAsync(0);
    await handOffToPolling(client, ['sw', 'c1']); // prefix of the read's key
    await vi.advanceTimersByTimeAsync(0);
    expect(queryFn).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(3000);
    expect(queryFn).toHaveBeenCalledTimes(5);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(queryFn).toHaveBeenCalledTimes(5); // seen active, now idle ⇒ the hand-off is over
    unsubscribe();
  });

  it('gives up at graceMs when the job never shows', async () => {
    const { queryFn, unsubscribe } = grid([{ cells: [] }]);
    await vi.advanceTimersByTimeAsync(0);
    await handOffToPolling(client, ['sw', 'c1'], { graceMs: 3500 });
    await vi.advanceTimersByTimeAsync(10_000);
    // 1 mount + 1 hand-off refetch + ticks at 1-4 s (the 4 s tick was scheduled at 3 s, before
    // the deadline); the deadline stops every tick after it.
    expect(queryFn).toHaveBeenCalledTimes(6);
    unsubscribe();
  });

  it("until: 'changed' ends at the first read that differs from the cached data", async () => {
    let n = 0;
    const answers = [{ v: 1 }, { v: 1 }, { v: 1 }, { v: 2 }];
    const queryFn = vi.fn(async () => answers[Math.min(n++, answers.length - 1)]);
    const observer = new QueryObserver(client, { queryKey: ['guias'], queryFn, ...jobPolling(() => false, 1000) });
    const unsubscribe = observer.subscribe(() => {});
    await vi.advanceTimersByTimeAsync(0);
    expect(queryFn).toHaveBeenCalledTimes(1); // an idle read never polls on its own
    await handOffToPolling(client, ['guias'], { until: 'changed' });
    await vi.advanceTimersByTimeAsync(2000);
    expect(queryFn).toHaveBeenCalledTimes(4); // hand-off refetch, then two ticks → v:2
    await vi.advanceTimersByTimeAsync(10_000);
    expect(queryFn).toHaveBeenCalledTimes(4);
    unsubscribe();
  });

  it('until: a predicate ends the hand-off once it says the effect landed', async () => {
    let n = 0;
    const answers = [{ v: 1, at: 'a' }, { v: 2, at: 'a' }, { v: 2, at: 'b' }];
    const queryFn = vi.fn(async () => answers[Math.min(n++, answers.length - 1)]);
    const observer = new QueryObserver(client, { queryKey: ['perfis'], queryFn, ...jobPolling(() => false, 1000) });
    const unsubscribe = observer.subscribe(() => {});
    await vi.advanceTimersByTimeAsync(0);
    await handOffToPolling(client, ['perfis'], {
      until: (d, before) => (d as { at: string }).at !== (before as { at: string }).at,
    });
    await vi.advanceTimersByTimeAsync(0);
    expect(queryFn).toHaveBeenCalledTimes(2); // v changed but `at` did not: still pending
    await vi.advanceTimersByTimeAsync(1000);
    expect(queryFn).toHaveBeenCalledTimes(3); // `at` moved ⇒ settled
    await vi.advanceTimersByTimeAsync(10_000);
    expect(queryFn).toHaveBeenCalledTimes(3);
    unsubscribe();
  });

  it('does not touch reads outside the handed-off key', async () => {
    const other = grid([{ cells: [] }], ['sw', 'c2', 'partes', null]);
    await vi.advanceTimersByTimeAsync(0);
    await handOffToPolling(client, ['sw', 'c1']);
    await vi.advanceTimersByTimeAsync(5000);
    expect(other.queryFn).toHaveBeenCalledTimes(1);
    other.unsubscribe();
  });
});
