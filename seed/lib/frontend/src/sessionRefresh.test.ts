/**
 * A deploy must never log a user out (2026-10-03).
 *
 * The owner's session on social.noctusai.com ended after three prod deploys in
 * one day. Each deploy swaps the product container AND restarts the cloudflared
 * tunnel, so for a few seconds requests answer a Cloudflare 502/530 or fail at
 * the network layer. Two client-side faults turned that into a logout:
 *
 *  1. `onTokenExpired` returned `null` both when Supabase REFUSED the refresh
 *     token and when the refresh could not get an answer — and `null` means
 *     "dead session" → `onUnauthenticated`.
 *  2. The dead-session handler called `supabase.auth.signOut()` with the
 *     supabase-js default scope `"global"`, which revokes EVERY refresh token
 *     the user holds — so core asked for the password too.
 *
 * These tests drive the real seed pieces (`createApiClient` +
 * `createSupabaseTokenRefresher` + `createDeadSessionHandler`) against a fake
 * supabase client shaped like supabase-js's `{ data, error }` results.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

import {
  createApiClient,
  isTransientHttpStatus,
  refreshWithBackoff,
  TransientAuthError,
  type RefreshAttempt,
} from './api';
import { classifySupabaseRefresh, createDeadSessionHandler, createSupabaseTokenRefresher } from './auth';

function jsonResponse(status: number, body: unknown = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const noSleep = () => Promise.resolve();

/** supabase-js `AuthRetryableFetchError` result: no response / 502-504. */
function retryable(status = 0) {
  return { data: { session: null, user: null }, error: { name: 'AuthRetryableFetchError', status, message: 'Failed to fetch' } };
}
/** supabase-js `AuthApiError` result: the Auth server answered. */
function refused(status = 400, code = 'refresh_token_already_used') {
  return { data: { session: null, user: null }, error: { name: 'AuthApiError', status, code, message: 'Invalid Refresh Token' } };
}
function ok(token = 'fresh') {
  return { data: { session: { access_token: token }, user: {} }, error: null };
}

function fakeSupabase(results: unknown[]) {
  const refreshSession = vi.fn();
  for (const r of results) refreshSession.mockResolvedValueOnce(r);
  const signOut = vi.fn().mockResolvedValue({ error: null });
  return { auth: { refreshSession, signOut } };
}

function fakeStore() {
  const setUser = vi.fn();
  return { setUser, useAuthStore: { getState: () => ({ setUser }) } };
}

function wire(supabase: ReturnType<typeof fakeSupabase>, store = fakeStore()) {
  const onUnauthenticated = vi.fn(createDeadSessionHandler(supabase, store.useAuthStore));
  const client = createApiClient({
    getBaseUrl: () => 'http://x',
    getAuthToken: async () => 'expired',
    onTokenExpired: createSupabaseTokenRefresher(supabase, { sleep: noSleep }),
    onUnauthenticated,
  });
  return { client, onUnauthenticated, store };
}

describe('a deploy window never logs the user out', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    Object.defineProperty(window, 'location', { value: { pathname: '/app' }, writable: true });
  });
  afterEach(() => vi.restoreAllMocks());

  it('keeps the session when every refresh attempt is a network error (tunnel restarting)', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(401, { detail: 'expired' }));
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    const supabase = fakeSupabase([retryable(0), retryable(0), retryable(503), retryable(0)]);
    const { client, onUnauthenticated, store } = wire(supabase);

    await expect(client.get('/api/x')).rejects.toThrow('[401]');

    expect(supabase.auth.refreshSession).toHaveBeenCalledTimes(4); // 1 + 3 backoff retries
    expect(onUnauthenticated).not.toHaveBeenCalled();
    expect(supabase.auth.signOut).not.toHaveBeenCalled();
    expect(store.setUser).not.toHaveBeenCalled();
  });

  it('keeps the session on an Auth 500 / 429 (answered, but not "this token is invalid")', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(401));
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    const supabase = fakeSupabase([refused(500, 'unexpected_failure'), refused(429, 'over_request_rate_limit'),
      refused(500, 'x'), refused(500, 'x')]);
    const { client, onUnauthenticated } = wire(supabase);

    await expect(client.get('/api/x')).rejects.toThrow('[401]');
    expect(onUnauthenticated).not.toHaveBeenCalled();
  });

  it('recovers transparently when the refresh succeeds after a transient failure', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse(401, { detail: 'expired' }))
      .mockResolvedValueOnce(jsonResponse(200, { ok: true }));
    const supabase = fakeSupabase([retryable(0), ok('fresh')]);
    const { client, onUnauthenticated } = wire(supabase);

    await expect(client.get('/api/x')).resolves.toEqual({ ok: true });
    expect(onUnauthenticated).not.toHaveBeenCalled();
    const retryHeaders = fetchMock.mock.calls[1][1]!.headers as Record<string, string>;
    expect(retryHeaders['Authorization']).toBe('Bearer fresh');
  });

  it('still logs out on an AUTHORITATIVE refusal — and never retries it', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(401));
    const supabase = fakeSupabase([refused(400, 'refresh_token_already_used')]);
    const { client, onUnauthenticated, store } = wire(supabase);

    await expect(client.get('/api/x')).rejects.toThrow('[401]');
    expect(supabase.auth.refreshSession).toHaveBeenCalledTimes(1);
    expect(onUnauthenticated).toHaveBeenCalledTimes(1);
    expect(store.setUser).toHaveBeenCalledWith(null);
  });

  it('a dead session signs out LOCALLY — never revokes the user\'s other sessions (core, other products)', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(401));
    const supabase = fakeSupabase([refused(400)]);
    const { client } = wire(supabase);

    await expect(client.get('/api/x')).rejects.toThrow('[401]');
    expect(supabase.auth.signOut).toHaveBeenCalledTimes(1);
    expect(supabase.auth.signOut).toHaveBeenCalledWith({ scope: 'local' });
  });

  it('concurrent 401s share ONE refresh (single-flight)', async () => {
    let n = 0;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (_url, init) => {
      const auth = (init!.headers as Record<string, string>)['Authorization'];
      n += 1;
      return auth === 'Bearer fresh' ? jsonResponse(200, { ok: true }) : jsonResponse(401);
    });
    const supabase = fakeSupabase([ok('fresh'), ok('fresh2'), ok('fresh3')]);
    const { client, onUnauthenticated } = wire(supabase);

    await Promise.all([client.get('/a'), client.get('/b'), client.get('/c')]);
    expect(supabase.auth.refreshSession).toHaveBeenCalledTimes(1);
    expect(onUnauthenticated).not.toHaveBeenCalled();
    expect(n).toBe(6);
  });

  it('a 5xx / Cloudflare 530 from the API itself never triggers a refresh or a logout', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(530, {}));
    const supabase = fakeSupabase([]);
    const { client, onUnauthenticated } = wire(supabase);
    await expect(client.get('/api/x')).rejects.toThrow('[530]');
    expect(supabase.auth.refreshSession).not.toHaveBeenCalled();
    expect(onUnauthenticated).not.toHaveBeenCalled();
  });
});

describe('createDeadSessionHandler', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'location', { value: { pathname: '/app' }, writable: true });
  });

  it('collapses a burst of dead-session signals into one sign-out', () => {
    const supabase = fakeSupabase([]);
    const store = fakeStore();
    const handle = createDeadSessionHandler(supabase, store.useAuthStore);
    handle(); handle(); handle();
    expect(supabase.auth.signOut).toHaveBeenCalledTimes(1);
    expect(store.setUser).toHaveBeenCalledTimes(1);
  });

  it('does nothing on a public auth route (no redirect loop)', () => {
    Object.defineProperty(window, 'location', { value: { pathname: '/sso' }, writable: true });
    const supabase = fakeSupabase([]);
    const handle = createDeadSessionHandler(supabase, fakeStore().useAuthStore);
    handle();
    expect(supabase.auth.signOut).not.toHaveBeenCalled();
  });
});

describe('refreshWithBackoff', () => {
  it('waits the configured delays between transient attempts, then throws TransientAuthError', async () => {
    const sleep = vi.fn().mockResolvedValue(undefined);
    const attempt = vi.fn(async (): Promise<RefreshAttempt> => ({ kind: 'transient', reason: 'HTTP 502' }));
    await expect(refreshWithBackoff(attempt, { delaysMs: [10, 20], sleep })).rejects.toBeInstanceOf(TransientAuthError);
    expect(attempt).toHaveBeenCalledTimes(3);
    expect(sleep.mock.calls.map((c) => c[0])).toEqual([10, 20]);
  });

  it('an attempt that throws counts as transient, not dead', async () => {
    const attempt = vi.fn()
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce({ kind: 'token', token: 't' });
    await expect(refreshWithBackoff(attempt, { sleep: noSleep })).resolves.toBe('t');
  });

  it('resolves null on "dead" immediately', async () => {
    const attempt = vi.fn(async (): Promise<RefreshAttempt> => ({ kind: 'dead' }));
    await expect(refreshWithBackoff(attempt, { sleep: noSleep })).resolves.toBeNull();
    expect(attempt).toHaveBeenCalledTimes(1);
  });
});

describe('classifiers', () => {
  it('isTransientHttpStatus', () => {
    for (const s of [0, null, undefined, 408, 425, 429, 500, 502, 503, 504, 520, 522, 524, 530]) {
      expect(isTransientHttpStatus(s as number | null | undefined)).toBe(true);
    }
    for (const s of [400, 401, 403, 404, 422]) expect(isTransientHttpStatus(s)).toBe(false);
  });

  it('classifySupabaseRefresh', () => {
    expect(classifySupabaseRefresh(ok('a'))).toEqual({ kind: 'token', token: 'a' });
    expect(classifySupabaseRefresh(retryable(0)).kind).toBe('transient');
    expect(classifySupabaseRefresh(retryable(504)).kind).toBe('transient');
    expect(classifySupabaseRefresh(refused(500)).kind).toBe('transient');
    expect(classifySupabaseRefresh(refused(429)).kind).toBe('transient');
    expect(classifySupabaseRefresh(refused(400)).kind).toBe('dead');
    expect(classifySupabaseRefresh(refused(401, 'session_not_found')).kind).toBe('dead');
    expect(classifySupabaseRefresh({ data: { session: null }, error: null }).kind).toBe('dead');
  });
});
