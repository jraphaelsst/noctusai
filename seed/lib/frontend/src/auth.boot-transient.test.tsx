/// <reference types="@testing-library/jest-dom" />
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

import {
  useSupabaseAuthInit,
  useSessionAuthInit,
  useAuthReconnecting,
  classifyBootSession,
  classifyBootMeStatus,
} from './auth';

function client(getSession: ReturnType<typeof vi.fn>) {
  return {
    auth: {
      getSession,
      getUser: vi.fn().mockResolvedValue({ data: { user: { id: 'u1' } }, error: null }),
      onAuthStateChange: vi.fn(() => ({ data: { subscription: { unsubscribe: vi.fn() } } })),
    },
  };
}

const retryable = { data: { session: null }, error: { name: 'AuthRetryableFetchError', status: 530 } };

beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
afterEach(() => vi.useRealTimers());

describe('boot verdict classification', () => {
  it('transient auth-server failure is not "no session"', () => {
    expect(classifyBootSession(retryable)).toEqual({ kind: 'transient' });
    expect(classifyBootSession({ data: { session: null }, error: { name: 'AuthApiError', status: 502 } })).toEqual({ kind: 'transient' });
    expect(classifyBootSession({ data: { session: null }, error: { name: 'AuthApiError', status: 400 } })).toEqual({ kind: 'none' });
    expect(classifyBootSession({ data: { session: null }, error: null })).toEqual({ kind: 'none' });
  });
  it('/api/auth/me statuses', () => {
    for (const s of [502, 503, 530, 408, 429]) expect(classifyBootMeStatus(s)).toBe('transient');
    for (const s of [401, 403]) expect(classifyBootMeStatus(s)).toBe('none');
    expect(classifyBootMeStatus(200)).toBe('ok');
  });
});

describe('useSupabaseAuthInit boot', () => {
  it('502/530/network at boot: no logout, shows reconnecting, retry restores the user', async () => {
    const user = { id: 'u1' };
    const getSession = vi.fn()
      .mockResolvedValueOnce(retryable)
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValue({ data: { session: { user } }, error: null });
    const setUser = vi.fn();
    const setInitialized = vi.fn();
    const sb = client(getSession);
    const { result } = renderHook(() => {
      useSupabaseAuthInit(sb, setUser, setInitialized);
      return useAuthReconnecting();
    });
    await waitFor(() => expect(result.current).toBe(true));
    expect(setUser).not.toHaveBeenCalled();
    expect(setInitialized).not.toHaveBeenCalled();
    await act(async () => { await vi.advanceTimersByTimeAsync(1_000); });
    await act(async () => { await vi.advanceTimersByTimeAsync(3_000); });
    await waitFor(() => expect(setUser).toHaveBeenCalledWith(user));
    expect(setUser).not.toHaveBeenCalledWith(null);
    expect(setInitialized).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(result.current).toBe(false));
  });

  it('a definitive "no session" answer still boots to signed-out', async () => {
    const getSession = vi.fn().mockResolvedValue({ data: { session: null }, error: null });
    const setUser = vi.fn();
    const sb = client(getSession);
    renderHook(() => useSupabaseAuthInit(sb, setUser));
    await waitFor(() => expect(setUser).toHaveBeenCalledWith(null));
  });
});

describe('useSessionAuthInit boot', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('530 then 200: no setUser(null), user restored after retry', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response('', { status: 530 }))
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValue(new Response(JSON.stringify({ user: { id: 'u', email: 'e' }, org: { id: 'o', name: 'n' } }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    const setUser = vi.fn();
    const setInitialized = vi.fn();
    renderHook(() => useSessionAuthInit(setUser, setInitialized));
    await act(async () => { await vi.advanceTimersByTimeAsync(1_000); });
    await act(async () => { await vi.advanceTimersByTimeAsync(3_000); });
    await waitFor(() => expect(setUser).toHaveBeenCalledWith({ id: 'u', email: 'e' }));
    expect(setUser).not.toHaveBeenCalledWith(null);
    expect(setInitialized).toHaveBeenCalledTimes(1);
  });

  it('real 401: signed out immediately', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 401 })));
    const setUser = vi.fn();
    const setInitialized = vi.fn();
    renderHook(() => useSessionAuthInit(setUser, setInitialized));
    await waitFor(() => expect(setUser).toHaveBeenCalledWith(null));
    expect(setInitialized).toHaveBeenCalled();
  });
});
