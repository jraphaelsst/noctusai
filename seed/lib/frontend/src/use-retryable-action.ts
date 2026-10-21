/**
 * `useRetryableAction` — the canonical automatic-retry wrapper for a process
 * that is NOT a query: an upload, an extraction re-run, a generation request.
 *
 * Same policy as the query client (`./retry`): a transient failure is retried
 * automatically, paced 1s → 3s → 9s (or the server's `Retry-After`); a
 * non-transient one stops immediately. When the attempts run out the hook
 * reports `status: 'error'` and `retry()` re-runs the SAME call (same
 * arguments) through the same paced attempts — wire it to the button
 * `RetryableError` renders:
 *
 *     const upload = useRetryableAction(
 *       (file: File) => mutation.mutateAsync({ file }),
 *       { isRetryable: isRetrySafeForWrite },        // a write: stricter
 *     );
 *     <button onClick={() => upload.run(file)} />
 *     {upload.status === 'error' && (
 *       <RetryableError error={upload.error} attempts={upload.attempt}
 *         onRetry={upload.retry} isRetrying={upload.isRunning} />
 *     )}
 *
 * For a WRITE, pass `isRetryable: isRetrySafeForWrite` unless the operation is
 * idempotent — the default `isTransientError` would re-send after a timeout,
 * which the server may already have processed.
 *
 * `run` never rejects: the outcome lives in `status` / `error` / `data`, and
 * `onError` / `onSuccess` fire once per run (after the LAST attempt), so a
 * caller that toasts does so once, not per attempt.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { autoRetryDelayMs, isTransientError, MAX_AUTO_RETRIES, retryAfterMs, MAX_RETRY_AFTER_MS, AUTO_RETRY_DELAYS_MS } from './retry';

export interface RetryPolicy {
  /** Automatic retries after the first attempt. Default 3. */
  maxRetries?: number;
  /** Waits before each retry. Default `AUTO_RETRY_DELAYS_MS` (1s, 3s, 9s). */
  delaysMs?: readonly number[];
  /** Which failures are retried. Default `isTransientError`; use
   *  `isRetrySafeForWrite` for a non-idempotent write. */
  isRetryable?: (err: unknown) => boolean;
  /** Injected for tests; defaults to `setTimeout`. */
  sleep?: (ms: number) => Promise<void>;
}

export interface RetryOutcome<T> {
  ok: boolean;
  data?: T;
  error?: unknown;
  /** Total attempts made (1 = no retry happened). */
  attempts: number;
}

const defaultSleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/**
 * The framework-free loop behind the hook. `onAttempt(n)` fires before each
 * attempt (1-based); `isCancelled()` is checked after every wait so an
 * unmounted/superseded run stops without another request.
 */
export async function runWithRetry<T>(
  fn: () => Promise<T>,
  policy: RetryPolicy = {},
  hooks: { onAttempt?: (attempt: number) => void; isCancelled?: () => boolean } = {},
): Promise<RetryOutcome<T>> {
  const maxRetries = policy.maxRetries ?? MAX_AUTO_RETRIES;
  const delays = policy.delaysMs ?? AUTO_RETRY_DELAYS_MS;
  const isRetryable = policy.isRetryable ?? isTransientError;
  const sleep = policy.sleep ?? defaultSleep;
  let attempt = 0;
  for (;;) {
    attempt += 1;
    hooks.onAttempt?.(attempt);
    try {
      const data = await fn();
      return { ok: true, data, attempts: attempt };
    } catch (error) {
      const retriesUsed = attempt - 1;
      const fromServer = retryAfterMs(error);
      const giveUp =
        retriesUsed >= maxRetries ||
        !isRetryable(error) ||
        (fromServer !== null && fromServer > MAX_RETRY_AFTER_MS) ||
        hooks.isCancelled?.() === true;
      if (giveUp) return { ok: false, error, attempts: attempt };
      await sleep(autoRetryDelayMs(retriesUsed, error, delays));
      if (hooks.isCancelled?.()) return { ok: false, error, attempts: attempt };
    }
  }
}

export type RetryableActionStatus = 'idle' | 'running' | 'retrying' | 'success' | 'error';

export interface RetryableActionOptions<T> extends RetryPolicy {
  onSuccess?: (data: T) => void;
  /** Fires once, after the last attempt. `retry` re-runs the same call. */
  onError?: (error: unknown, ctx: { attempts: number; retry: () => void }) => void;
}

export interface RetryableAction<TArgs extends unknown[], T> {
  /** Start the process. Supersedes a run still in flight. Never rejects. */
  run: (...args: TArgs) => Promise<RetryOutcome<T>>;
  /** Re-run the last call with the same arguments (the button). */
  retry: () => Promise<RetryOutcome<T>>;
  reset: () => void;
  status: RetryableActionStatus;
  /** Attempt in progress, or total attempts of the finished run (1-based; 0 = idle). */
  attempt: number;
  error: unknown;
  data: T | undefined;
  /** `running` or `retrying` — drive the button spinner off this. */
  isRunning: boolean;
}

export function useRetryableAction<TArgs extends unknown[], T>(
  fn: (...args: TArgs) => Promise<T>,
  options: RetryableActionOptions<T> = {},
): RetryableAction<TArgs, T> {
  const [status, setStatus] = useState<RetryableActionStatus>('idle');
  const [attempt, setAttempt] = useState(0);
  const [error, setError] = useState<unknown>(null);
  const [data, setData] = useState<T | undefined>(undefined);

  // Latest fn/options without re-creating run/retry on every render.
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const optionsRef = useRef(options);
  optionsRef.current = options;
  const lastArgs = useRef<TArgs | null>(null);
  const runId = useRef(0);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      runId.current += 1; // cancels any in-flight loop
    };
  }, []);

  const run = useCallback(async (...args: TArgs): Promise<RetryOutcome<T>> => {
    lastArgs.current = args;
    const id = ++runId.current;
    const live = () => mounted.current && id === runId.current;
    setError(null);
    const outcome = await runWithRetry(() => fnRef.current(...args), optionsRef.current, {
      isCancelled: () => !live(),
      onAttempt: (n) => {
        if (!live()) return;
        setAttempt(n);
        setStatus(n === 1 ? 'running' : 'retrying');
      },
    });
    if (!live()) return outcome;
    if (outcome.ok) {
      setData(outcome.data);
      setStatus('success');
      optionsRef.current.onSuccess?.(outcome.data as T);
    } else {
      setError(outcome.error);
      setStatus('error');
      optionsRef.current.onError?.(outcome.error, {
        attempts: outcome.attempts,
        retry: () => {
          if (lastArgs.current) void run(...lastArgs.current);
        },
      });
    }
    return outcome;
  }, []);

  const retry = useCallback(async (): Promise<RetryOutcome<T>> => {
    if (!lastArgs.current) return { ok: false, error: new Error('Nada para tentar novamente.'), attempts: 0 };
    return run(...lastArgs.current);
  }, [run]);

  const reset = useCallback(() => {
    runId.current += 1;
    lastArgs.current = null;
    setStatus('idle');
    setAttempt(0);
    setError(null);
    setData(undefined);
  }, []);

  return {
    run,
    retry,
    reset,
    status,
    attempt,
    error,
    data,
    isRunning: status === 'running' || status === 'retrying',
  };
}
