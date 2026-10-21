/**
 * Canonical automatic-retry policy for every product SPA.
 *
 * Owner request (2026-10-21): "retry automatically when things go south,
 * paced; after a few attempts stop and give the user a button that triggers
 * the same process again." This module is the ONE place that answers:
 *
 *   1. Which failures are worth retrying at all — `isTransientError`.
 *      Only failures that can plausibly succeed on a second try: no HTTP
 *      response (network drop / timeout) or an HTTP 408 / 425 / 429 / 5xx.
 *      Never a 4xx like 401/403/404/422 — the same request will get the same
 *      answer, and retrying only stretches the spinner in front of it.
 *   2. How the attempts are paced — `AUTO_RETRY_DELAYS_MS` (1s, 3s, 9s), or
 *      the server's own `Retry-After` on a 429/503 when it sent one.
 *   3. Which WRITES are safe to re-send — `isRetrySafeForWrite`. Writes are
 *      not idempotent, so mutations do NOT auto-retry by default; a mutation
 *      or process that opts in uses this stricter classifier, which only
 *      accepts failures where the server provably did not act on the request.
 *   4. A short, user-facing reason CLASS for a failure — `describeFailure`.
 *      Portuguese, never the raw server text (which can be an HTML error page,
 *      a stack trace, or an English library message).
 *
 * Consumers: `createQueryClient` (queries default to this policy),
 * `useRetryableAction` (non-query processes), and the `RetryableError` /
 * `QueryErrorState` components (the button shown once the attempts ran out).
 */
import { ApiError, isTransientHttpStatus } from './api';

/** Waits before each automatic retry: 1s, 3s, 9s (≈13s worst case). */
export const AUTO_RETRY_DELAYS_MS: readonly number[] = [1_000, 3_000, 9_000];

/** Automatic retries after the first attempt (so up to 4 attempts in total). */
export const MAX_AUTO_RETRIES = AUTO_RETRY_DELAYS_MS.length;

/**
 * A server `Retry-After` longer than this is not honoured by waiting: the
 * automatic attempts stop and the user gets the button instead. Holding a
 * spinner for a minute is worse UX than saying "try again shortly".
 */
export const MAX_RETRY_AFTER_MS = 30_000;

function hasName(err: unknown, name: string): boolean {
  return typeof err === 'object' && err !== null && (err as { name?: unknown }).name === name;
}

/**
 * A raw `fetch()` network rejection. Browsers reject with a `TypeError`
 * whose message names the fetch ("Failed to fetch" — Chromium, "Load failed"
 * — Safari, "NetworkError when attempting to fetch resource." — Firefox).
 * Matched on the message so a genuine programming `TypeError` inside a
 * `queryFn` (`undefined.foo`) is NOT mistaken for a transient failure.
 */
function isFetchNetworkTypeError(err: unknown): boolean {
  return err instanceof TypeError && /fetch|network|load failed/i.test(err.message);
}

/**
 * True when a failure can plausibly succeed if the SAME request is sent again.
 *
 * - `ApiError` with no status (network drop / timeout) or 408/425/429/5xx → yes.
 * - `ApiError` with any other status (4xx, or a 200 whose body was not JSON —
 *   a deploy/routing mismatch that a retry will not fix) → no.
 * - A raw `fetch` network rejection (`TypeError: Failed to fetch`) → yes; a
 *   `TimeoutError` → yes. A programming `TypeError` → no.
 * - An `AbortError` → no: something cancelled the request on purpose.
 * - Anything else (a bug in a `queryFn`, a validation error thrown by product
 *   code) → no. Retrying a deterministic exception only delays the error.
 */
export function isTransientError(err: unknown): boolean {
  if (err instanceof ApiError) return isTransientHttpStatus(err.status);
  if (hasName(err, 'TimeoutError')) return true;
  if (hasName(err, 'AbortError')) return false;
  if (isFetchNetworkTypeError(err)) return true;
  return false;
}

/**
 * Stricter classifier for a WRITE (upload, create, re-queue) that opts into
 * automatic retries: only failures where the server provably did NOT act on
 * the request. A refused connection (`transport: 'network'`), 408, 425, 429,
 * 502 and 503 qualify; a timeout, 500 or 504 do not — the server may have
 * processed the request before the response was lost, and re-sending would
 * duplicate the write. Those surface the button immediately, so the user
 * decides after checking the screen.
 */
export function isRetrySafeForWrite(err: unknown): boolean {
  if (err instanceof ApiError) {
    if (err.status === null) return err.transport === 'network';
    return [408, 425, 429, 502, 503].includes(err.status);
  }
  // A raw fetch rejection with no wrapper: the request never got a response.
  // Without the ApiError transport tag we cannot tell a refused connection
  // from a lost response, so a write does not risk it.
  return false;
}

/** The server's `Retry-After` in ms, for a 429/503 that carried one. */
export function retryAfterMs(err: unknown): number | null {
  if (!(err instanceof ApiError)) return null;
  if (err.status !== 429 && err.status !== 503) return null;
  if (err.retryAfterSeconds === null || err.retryAfterSeconds === undefined) return null;
  return Math.max(0, err.retryAfterSeconds * 1000);
}

/**
 * Delay before retry number `retryIndex` (0-based: 0 = the wait after the
 * first failure). The server's `Retry-After` wins when present; otherwise the
 * canonical schedule (clamped to its last step).
 */
export function autoRetryDelayMs(
  retryIndex: number,
  err?: unknown,
  delaysMs: readonly number[] = AUTO_RETRY_DELAYS_MS,
): number {
  const fromServer = retryAfterMs(err);
  if (fromServer !== null) return Math.min(fromServer, MAX_RETRY_AFTER_MS);
  if (delaysMs.length === 0) return 0;
  return delaysMs[Math.min(Math.max(retryIndex, 0), delaysMs.length - 1)];
}

/**
 * Whether to retry after `failureCount` previous failures (TanStack Query's
 * `retry(failureCount, error)` contract: 0 on the first failure).
 */
export function shouldAutoRetry(
  failureCount: number,
  err: unknown,
  options: { maxRetries?: number; isRetryable?: (err: unknown) => boolean } = {},
): boolean {
  const max = options.maxRetries ?? MAX_AUTO_RETRIES;
  const isRetryable = options.isRetryable ?? isTransientError;
  if (failureCount >= max) return false;
  if (!isRetryable(err)) return false;
  const fromServer = retryAfterMs(err);
  // The server asked for a longer pause than we are willing to hold a
  // spinner for — stop and hand the decision to the user.
  if (fromServer !== null && fromServer > MAX_RETRY_AFTER_MS) return false;
  return true;
}

/**
 * Ready-to-spread TanStack Query options for a MUTATION that opts into
 * automatic retries (mutations default to none). Uses the write-safe
 * classifier unless the mutation is known to be idempotent. Spread it into
 * the mutation's options object (`useCacheWriteMutation` forwards it):
 *
 *     { mutationFn, ...autoRetryMutationOptions() }
 *     { mutationFn, ...autoRetryMutationOptions({ idempotent: true }) }
 */
export function autoRetryMutationOptions(options: { idempotent?: boolean } = {}) {
  const isRetryable = options.idempotent ? isTransientError : isRetrySafeForWrite;
  return {
    retry: (failureCount: number, err: unknown) => shouldAutoRetry(failureCount, err, { isRetryable }),
    retryDelay: (failureCount: number, err: unknown) => autoRetryDelayMs(failureCount, err),
  };
}

/**
 * A short Portuguese reason CLASS for a failure — never the server's raw text.
 * Shown under "Não foi possível carregar." by `RetryableError`.
 */
export function describeFailure(err: unknown): string {
  if (err instanceof ApiError) {
    const s = err.status;
    if (s === null) {
      return err.transport === 'timeout'
        ? 'O servidor demorou demais para responder.'
        : 'Sem conexão com o servidor.';
    }
    if (s === 408) return 'O servidor demorou demais para responder.';
    if (s === 429) return 'Muitas solicitações seguidas — o servidor pediu uma pausa.';
    if (s >= 500) return 'O servidor está instável no momento.';
    if (s === 401) return 'Sua sessão expirou.';
    if (s === 403) return 'Você não tem permissão para acessar isto.';
    if (s === 404) return 'Não encontrado.';
    if (s >= 400) return 'A solicitação foi recusada.';
    return 'Resposta inesperada do servidor.';
  }
  if (hasName(err, 'TimeoutError')) return 'O servidor demorou demais para responder.';
  if (isFetchNetworkTypeError(err)) return 'Sem conexão com o servidor.';
  return 'Ocorreu um erro inesperado.';
}
