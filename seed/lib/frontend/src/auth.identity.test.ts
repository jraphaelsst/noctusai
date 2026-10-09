/**
 * Boot/focus identity check of useSupabaseAuthInit: the stored session is a
 * claim, `auth.getUser()` is the verdict. Only an auth REJECTION signs out.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { useSupabaseAuthInit } from './auth';

const SESSION = { user: { id: 'u1', email: 'a@x.com' } };

function makeSupabase(getUser: () => Promise<unknown>) {
  return {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: SESSION } }),
      getUser: vi.fn(getUser),
      signOut: vi.fn().mockResolvedValue({ error: null }),
      onAuthStateChange: vi.fn(() => ({ data: { subscription: { unsubscribe: vi.fn() } } })),
    },
  };
}

const apiErr = (status: number, code?: string) => ({ name: 'AuthApiError', status, code, message: 'x' });

function setVisibility(v: 'visible' | 'hidden') {
  Object.defineProperty(document, 'visibilityState', { value: v, configurable: true });
  document.dispatchEvent(new Event('visibilitychange'));
}

describe('useSupabaseAuthInit identity check', () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 204 });
  beforeEach(() => {
    fetchMock.mockClear();
    vi.stubGlobal('fetch', fetchMock);
    vi.spyOn(console, 'warn').mockImplementation(() => {});
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('auth rejection on boot: local signOut + cookie drop + setUser(null)', async () => {
    const sb = makeSupabase(async () => ({ data: { user: null }, error: apiErr(403, 'session_not_found') }));
    const setUser = vi.fn();
    renderHook(() => useSupabaseAuthInit(sb, setUser));
    await waitFor(() => expect(setUser).toHaveBeenLastCalledWith(null));
    expect(sb.auth.signOut).toHaveBeenCalledWith({ scope: 'local' });
    expect(fetchMock.mock.calls.some((c) => String(c[0]).endsWith('/api/auth/logout') && c[1]?.credentials === 'include')).toBe(true);
  });

  it('AuthSessionMissingError also counts as rejection', async () => {
    const sb = makeSupabase(async () => ({ data: { user: null }, error: { name: 'AuthSessionMissingError', message: 'm' } }));
    const setUser = vi.fn();
    renderHook(() => useSupabaseAuthInit(sb, setUser));
    await waitFor(() => expect(setUser).toHaveBeenLastCalledWith(null));
  });

  it.each([
    ['retryable fetch error', { name: 'AuthRetryableFetchError', status: 0, message: 'net' }],
    ['5xx api error', apiErr(503)],
  ])('%s keeps the session', async (_n, error) => {
    const sb = makeSupabase(async () => ({ data: { user: null }, error }));
    const setUser = vi.fn();
    renderHook(() => useSupabaseAuthInit(sb, setUser));
    await waitFor(() => expect(sb.auth.getUser).toHaveBeenCalled());
    await act(async () => {});
    expect(sb.auth.signOut).not.toHaveBeenCalled();
    expect(setUser).not.toHaveBeenCalledWith(null);
  });

  it('thrown network failure keeps the session', async () => {
    const sb = makeSupabase(async () => { throw new TypeError('Failed to fetch'); });
    const setUser = vi.fn();
    renderHook(() => useSupabaseAuthInit(sb, setUser));
    await waitFor(() => expect(sb.auth.getUser).toHaveBeenCalled());
    await act(async () => {});
    expect(sb.auth.signOut).not.toHaveBeenCalled();
  });

  it('throttles refocus checks to once per 60s', async () => {
    const sb = makeSupabase(async () => ({ data: { user: SESSION.user }, error: null }));
    renderHook(() => useSupabaseAuthInit(sb, vi.fn()));
    await waitFor(() => expect(sb.auth.getUser).toHaveBeenCalledTimes(1));
    const now = Date.now();
    const spy = vi.spyOn(Date, 'now');
    spy.mockReturnValue(now + 10_000);
    act(() => setVisibility('visible'));
    expect(sb.auth.getUser).toHaveBeenCalledTimes(1);
    spy.mockReturnValue(now + 61_000);
    act(() => setVisibility('hidden'));
    expect(sb.auth.getUser).toHaveBeenCalledTimes(1);
    act(() => setVisibility('visible'));
    await waitFor(() => expect(sb.auth.getUser).toHaveBeenCalledTimes(2));
  });
});
