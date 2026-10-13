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

import { jobPolling, type JobPollingQuery } from './job-polling';

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
