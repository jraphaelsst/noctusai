/**
 * The canonical retry policy: which failures are transient, which writes are
 * safe to re-send, the paced schedule, Retry-After, and the reason classes.
 */
import { describe, expect, it } from 'vitest';

import { ApiError } from './api';
import {
  AUTO_RETRY_DELAYS_MS,
  MAX_AUTO_RETRIES,
  autoRetryDelayMs,
  autoRetryMutationOptions,
  describeFailure,
  isRetrySafeForWrite,
  isTransientError,
  retryAfterMs,
  shouldAutoRetry,
} from './retry';

const http = (status: number, retryAfter: number | null = null) =>
  new ApiError(status, 'x', undefined, retryAfter);
const network = () => new ApiError(null, 'x', undefined, null, 'network');
const timeout = () => new ApiError(null, 'x', undefined, null, 'timeout');

describe('isTransientError', () => {
  it.each([408, 425, 429, 500, 502, 503, 504, 520, 530])('HTTP %i is transient', (s) => {
    expect(isTransientError(http(s))).toBe(true);
  });

  it.each([400, 401, 403, 404, 409, 410, 422])('HTTP %i is NOT transient', (s) => {
    expect(isTransientError(http(s))).toBe(false);
  });

  it('a 200 with a non-JSON body (deploy/routing mismatch) is not transient', () => {
    expect(isTransientError(http(200))).toBe(false);
  });

  it('no response (network / timeout) is transient', () => {
    expect(isTransientError(network())).toBe(true);
    expect(isTransientError(timeout())).toBe(true);
    expect(isTransientError(new ApiError(null, 'legacy, untagged'))).toBe(true);
  });

  it('a raw fetch network TypeError is transient; a programming TypeError is not', () => {
    expect(isTransientError(new TypeError('Failed to fetch'))).toBe(true);
    expect(isTransientError(new TypeError('Load failed'))).toBe(true);
    expect(isTransientError(new TypeError("Cannot read properties of undefined (reading 'x')"))).toBe(false);
  });

  it('TimeoutError retries, a deliberate AbortError does not', () => {
    expect(isTransientError(new DOMException('t', 'TimeoutError'))).toBe(true);
    expect(isTransientError(new DOMException('a', 'AbortError'))).toBe(false);
  });

  it('an arbitrary Error from product code is not retried', () => {
    expect(isTransientError(new Error('validation'))).toBe(false);
    expect(isTransientError('boom')).toBe(false);
    expect(isTransientError(null)).toBe(false);
  });
});

describe('isRetrySafeForWrite', () => {
  it('accepts only failures where the server did not act', () => {
    for (const s of [408, 425, 429, 502, 503]) expect(isRetrySafeForWrite(http(s))).toBe(true);
    expect(isRetrySafeForWrite(network())).toBe(true);
  });

  it('refuses a timeout / 500 / 504 / 4xx — the write may have landed', () => {
    for (const s of [500, 504, 400, 404, 422]) expect(isRetrySafeForWrite(http(s))).toBe(false);
    expect(isRetrySafeForWrite(timeout())).toBe(false);
    expect(isRetrySafeForWrite(new ApiError(null, 'untagged'))).toBe(false);
    expect(isRetrySafeForWrite(new TypeError('Failed to fetch'))).toBe(false);
  });
});

describe('backoff schedule', () => {
  it('is 1s, 3s, 9s with 3 retries', () => {
    expect([...AUTO_RETRY_DELAYS_MS]).toEqual([1000, 3000, 9000]);
    expect(MAX_AUTO_RETRIES).toBe(3);
    expect([0, 1, 2].map((i) => autoRetryDelayMs(i, http(503)))).toEqual([1000, 3000, 9000]);
  });

  it('clamps past the last step', () => {
    expect(autoRetryDelayMs(7, http(500))).toBe(9000);
  });

  it('honours Retry-After on 429/503 (capped at 30s), ignores it elsewhere', () => {
    expect(retryAfterMs(http(429, 5))).toBe(5000);
    expect(autoRetryDelayMs(0, http(503, 2))).toBe(2000);
    expect(autoRetryDelayMs(0, http(429, 120))).toBe(30_000);
    expect(retryAfterMs(http(500, 5))).toBeNull();
    expect(autoRetryDelayMs(1, http(500, 5))).toBe(3000);
  });
});

describe('shouldAutoRetry (TanStack retry contract: failureCount 0 on first failure)', () => {
  it('retries a transient failure 3 times, then stops', () => {
    const err = http(502);
    expect([0, 1, 2, 3].map((n) => shouldAutoRetry(n, err))).toEqual([true, true, true, false]);
  });

  it('never retries a 4xx', () => {
    expect(shouldAutoRetry(0, http(404))).toBe(false);
    expect(shouldAutoRetry(0, http(401))).toBe(false);
    expect(shouldAutoRetry(0, http(422))).toBe(false);
  });

  it('stops when the server asks for a pause longer than 30s', () => {
    expect(shouldAutoRetry(0, http(429, 10))).toBe(true);
    expect(shouldAutoRetry(0, http(429, 60))).toBe(false);
  });

  it('autoRetryMutationOptions uses the write-safe classifier unless idempotent', () => {
    const write = autoRetryMutationOptions();
    expect(write.retry(0, timeout())).toBe(false);
    expect(write.retry(0, http(503))).toBe(true);
    const idem = autoRetryMutationOptions({ idempotent: true });
    expect(idem.retry(0, timeout())).toBe(true);
    expect(idem.retryDelay(1, http(500))).toBe(3000);
  });
});

describe('describeFailure — reason classes, never the server text', () => {
  it('maps each class to Portuguese copy', () => {
    expect(describeFailure(network())).toBe('Sem conexão com o servidor.');
    expect(describeFailure(timeout())).toBe('O servidor demorou demais para responder.');
    expect(describeFailure(http(503))).toBe('O servidor está instável no momento.');
    expect(describeFailure(http(429))).toMatch(/pausa/);
    expect(describeFailure(http(404))).toBe('Não encontrado.');
    expect(describeFailure(http(403))).toMatch(/permissão/);
    expect(describeFailure(new Error('<html>stack trace</html>'))).toBe('Ocorreu um erro inesperado.');
  });

  it('does not leak the ApiError message', () => {
    const e = new ApiError(500, 'psycopg2.OperationalError: connection refused');
    expect(describeFailure(e)).not.toMatch(/psycopg/);
  });
});
