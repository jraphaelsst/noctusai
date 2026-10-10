/**
 * 2026-10-10: every core redeploy logged users out — `/api/auth/me` failed
 * transiently and `fetchProfile`'s bare `catch` cleared the tokens. A failure
 * while the session is still held must KEEP it and retry; only the api
 * client's authoritative 401 path (`onUnauthenticated`, which clears the
 * tokens) ends it.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, act } from '@testing-library/react';
import React from 'react';

const get = vi.fn();
const clearToken = vi.fn();
let held = true;

vi.mock('./api', () => ({
  api: { get: (...a: unknown[]) => get(...a), post: vi.fn() },
  clearToken: () => clearToken(),
  setToken: vi.fn(),
  setRefreshToken: vi.fn(),
  getRefreshToken: () => null,
  isAuthenticated: () => held,
}));
vi.mock('@noctusai/lib/components', () => ({ MfaChallengeHost: () => null }));
vi.mock('@noctusai/lib/design-system/useActivityRefresh', () => ({ useActivityRefresh: () => undefined }));

import { AuthProvider, useAuth, PROFILE_RETRY_DELAYS_MS } from './auth-context';

let captured: ReturnType<typeof useAuth>;
function Probe() {
  captured = useAuth();
  return null;
}

async function flushRetries() {
  for (const ms of PROFILE_RETRY_DELAYS_MS) {
    await act(async () => { await vi.advanceTimersByTimeAsync(ms); });
  }
}

describe('core fetchProfile on a transient /api/auth/me failure', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    get.mockReset();
    clearToken.mockReset();
    held = true;
  });
  afterEach(() => { vi.useRealTimers(); });

  it('keeps the session and retries until /me answers', async () => {
    get
      .mockRejectedValueOnce(new Error('[502] Bad Gateway'))
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValue({ user: { id: 'u1', role: 'admin' }, organization: null });
    await act(async () => { render(<AuthProvider><Probe /></AuthProvider>); });
    await flushRetries();
    expect(clearToken).not.toHaveBeenCalled();
    expect(captured.user?.id).toBe('u1');
    expect(captured.unavailable).toBe(false);
    expect(get).toHaveBeenCalledTimes(3);
  });

  it('after the backoff is exhausted: unavailable, session still held, never cleared', async () => {
    get.mockRejectedValue(new Error('[503] Service Unavailable'));
    await act(async () => { render(<AuthProvider><Probe /></AuthProvider>); });
    await flushRetries();
    expect(clearToken).not.toHaveBeenCalled();
    expect(captured.loading).toBe(false);
    expect(captured.unavailable).toBe(true);
    expect(captured.user).toBeNull();
  });

  it('a dead session (the 401 path already cleared the tokens) is not retried', async () => {
    get.mockImplementation(async () => { held = false; throw new Error('[401] expired'); });
    await act(async () => { render(<AuthProvider><Probe /></AuthProvider>); });
    await flushRetries();
    expect(get).toHaveBeenCalledTimes(1);
    expect(captured.unavailable).toBe(false);
    expect(captured.user).toBeNull();
  });
});
