/**
 * useRetryableAction / runWithRetry — paced automatic attempts for a process
 * that is not a query, then `status: 'error'` + `retry()` re-running the SAME
 * call.
 */
import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ApiError } from './api';
import { isRetrySafeForWrite } from './retry';
import { runWithRetry, useRetryableAction } from './use-retryable-action';

const http = (s: number) => new ApiError(s, 'x');

function recordingSleep() {
  const waits: number[] = [];
  return { waits, sleep: async (ms: number) => void waits.push(ms) };
}

describe('runWithRetry', () => {
  it('retries transient failures paced 1s/3s/9s, then gives up after 4 attempts', async () => {
    const { waits, sleep } = recordingSleep();
    const fn = vi.fn().mockRejectedValue(http(503));
    const out = await runWithRetry(fn, { sleep });
    expect(out).toMatchObject({ ok: false, attempts: 4 });
    expect(fn).toHaveBeenCalledTimes(4);
    expect(waits).toEqual([1000, 3000, 9000]);
  });

  it('succeeds on a later attempt', async () => {
    const { sleep } = recordingSleep();
    const fn = vi.fn().mockRejectedValueOnce(http(502)).mockResolvedValueOnce('ok');
    expect(await runWithRetry(fn, { sleep })).toEqual({ ok: true, data: 'ok', attempts: 2 });
  });

  it('does not retry a non-transient failure', async () => {
    const { waits, sleep } = recordingSleep();
    const fn = vi.fn().mockRejectedValue(http(422));
    expect(await runWithRetry(fn, { sleep })).toMatchObject({ ok: false, attempts: 1 });
    expect(waits).toEqual([]);
  });

  it('a write with isRetrySafeForWrite does not re-send after a timeout', async () => {
    const { sleep } = recordingSleep();
    const fn = vi.fn().mockRejectedValue(new ApiError(null, 't', undefined, null, 'timeout'));
    const out = await runWithRetry(fn, { sleep, isRetryable: isRetrySafeForWrite });
    expect(out.attempts).toBe(1);
  });

  it('stops when cancelled during a wait', async () => {
    let cancelled = false;
    const fn = vi.fn().mockRejectedValue(http(500));
    const out = await runWithRetry(fn, { sleep: async () => { cancelled = true; } }, { isCancelled: () => cancelled });
    expect(out.attempts).toBe(1);
    expect(fn).toHaveBeenCalledTimes(1);
  });
});

describe('useRetryableAction', () => {
  it('auto-attempts, ends in error, then retry() re-runs the same call with the same args', async () => {
    const { sleep } = recordingSleep();
    const fn = vi.fn().mockRejectedValue(http(503));
    const onError = vi.fn();
    const { result } = renderHook(() => useRetryableAction(fn, { sleep, onError }));

    await act(async () => {
      await result.current.run('arquivo.pdf', 7);
    });
    expect(result.current.status).toBe('error');
    expect(result.current.attempt).toBe(4);
    expect(fn).toHaveBeenCalledTimes(4);
    expect(fn).toHaveBeenLastCalledWith('arquivo.pdf', 7);
    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError.mock.calls[0][1].attempts).toBe(4);

    fn.mockResolvedValueOnce('feito');
    await act(async () => {
      await result.current.retry();
    });
    expect(fn).toHaveBeenCalledTimes(5);
    expect(fn).toHaveBeenLastCalledWith('arquivo.pdf', 7);
    expect(result.current.status).toBe('success');
    expect(result.current.data).toBe('feito');
    expect(result.current.error).toBeNull();
  });

  it('reports running → retrying while attempts are in flight', async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => { release = r; });
    const fn = vi.fn().mockRejectedValueOnce(http(500)).mockResolvedValueOnce(1);
    const { result } = renderHook(() =>
      useRetryableAction(fn, { sleep: () => gate }),
    );
    let p!: Promise<unknown>;
    act(() => { p = result.current.run(); });
    await waitFor(() => expect(result.current.status).toBe('running'));
    expect(result.current.isRunning).toBe(true);
    await act(async () => { release(); await p; });
    expect(result.current.status).toBe('success');
    expect(result.current.attempt).toBe(2);
  });

  it('onError ctx.retry re-runs the last call', async () => {
    const { sleep } = recordingSleep();
    const fn = vi.fn().mockRejectedValueOnce(http(404)).mockResolvedValueOnce('ok');
    let retryFromToast: (() => void) | undefined;
    const { result } = renderHook(() =>
      useRetryableAction(fn, { sleep, onError: (_e, ctx) => { retryFromToast = ctx.retry; } }),
    );
    await act(async () => { await result.current.run('x'); });
    expect(result.current.status).toBe('error');
    await act(async () => { retryFromToast!(); });
    await waitFor(() => expect(result.current.status).toBe('success'));
    expect(fn).toHaveBeenLastCalledWith('x');
  });
});
