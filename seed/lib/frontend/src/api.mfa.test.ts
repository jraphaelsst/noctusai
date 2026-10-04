/**
 * api client — `403 mfa_required` interceptor + mfaChallenge broker.
 */
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { createApiClient, ApiError } from './api';
import { mfaChallenge } from './mfaChallenge';

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

let unsub: (() => void) | null = null;
afterEach(() => {
  unsub?.();
  unsub = null;
  mfaChallenge.settle(false);
  vi.unstubAllGlobals();
});

function setup(responder: (url: string, n: number) => Response) {
  const calls: string[] = [];
  const counts: Record<string, number> = {};
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    calls.push(url);
    counts[url] = (counts[url] ?? 0) + 1;
    return responder(url, counts[url]);
  }));
  const onMfaVerified = vi.fn();
  const api = createApiClient({
    getBaseUrl: () => 'http://x',
    getAuthToken: async () => 't',
    onMfaVerified,
  });
  return { api, calls, onMfaVerified };
}

describe('mfa interceptor', () => {
  let opened: number;
  beforeEach(() => {
    opened = 0;
  });

  it('concurrent 403s open ONE challenge; both calls are retried after verify', async () => {
    const { api, calls, onMfaVerified } = setup((url, n) =>
      n === 1 ? json(403, { code: 'mfa_required', enrolled: true }) : json(200, { ok: url }),
    );
    unsub = mfaChallenge.subscribe(() => {
      if (mfaChallenge.getCurrent()) opened += 1;
    });
    const a = api.get('/api/a');
    const b = api.get('/api/b');
    await vi.waitFor(() => expect(mfaChallenge.getCurrent()).not.toBeNull());
    expect(mfaChallenge.getCurrent()!.enrolled).toBe(true);
    await mfaChallenge.getCurrent()!.onVerified({ aal: 'aal2', access_token: 'new' });
    mfaChallenge.settle(true);
    await expect(a).resolves.toEqual({ ok: 'http://x/api/a' });
    await expect(b).resolves.toEqual({ ok: 'http://x/api/b' });
    expect(opened).toBe(1);
    expect(onMfaVerified).toHaveBeenCalledWith({ aal: 'aal2', access_token: 'new' });
    expect(calls.filter((c) => c.endsWith('/api/a'))).toHaveLength(2);
    expect(calls.filter((c) => c.endsWith('/api/b'))).toHaveLength(2);
  });

  it('cancel rejects every waiting call with the original 403', async () => {
    const { api } = setup(() => json(403, { code: 'mfa_required', enrolled: false }));
    unsub = mfaChallenge.subscribe(() => {});
    const a = api.get('/api/a').catch((e) => e);
    const b = api.post('/api/b', { x: 1 }).catch((e) => e);
    await vi.waitFor(() => expect(mfaChallenge.getCurrent()).not.toBeNull());
    expect(mfaChallenge.getCurrent()!.enrolled).toBe(false);
    mfaChallenge.settle(false);
    for (const err of [await a, await b]) {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).status).toBe(403);
      expect((err as ApiError).code).toBe('mfa_required');
    }
  });

  it('without a mounted host the original 403 is thrown (no hang)', async () => {
    const { api } = setup(() => json(403, { code: 'mfa_required', enrolled: true }));
    await expect(api.get('/api/a')).rejects.toMatchObject({ status: 403 });
  });

  it('other 403s are untouched', async () => {
    const { api } = setup(() => json(403, { detail: 'nope' }));
    unsub = mfaChallenge.subscribe(() => {});
    await expect(api.get('/api/a')).rejects.toMatchObject({ status: 403 });
    expect(mfaChallenge.getCurrent()).toBeNull();
  });

  it('the dialog transport never re-raises the challenge', async () => {
    const { api } = setup(() => json(403, { code: 'mfa_required', enrolled: true }));
    unsub = mfaChallenge.subscribe(() => {});
    const a = api.get('/api/a').catch(() => null);
    await vi.waitFor(() => expect(mfaChallenge.getCurrent()).not.toBeNull());
    await expect(mfaChallenge.getCurrent()!.api.get('/api/auth/mfa/status')).rejects.toMatchObject({ status: 403 });
    mfaChallenge.settle(false);
    await a;
  });
});
