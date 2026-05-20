/**
 * Tests for the Wave-3 HttpOnly-cookie session auth helpers:
 *   - useSessionAuthInit (boot-time /api/auth/me)
 *   - loginWithSession (POST /api/auth/login)
 *   - logoutSession (POST /api/auth/logout)
 *
 * Mocks `globalThis.fetch` per-test. `useAuthReady` regression
 * coverage confirms the existing global "auth restore resolved"
 * signal still flips under the new boot path.
 */
/// <reference types="@testing-library/jest-dom" />
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

import {
  useSessionAuthInit,
  loginWithSession,
  logoutSession,
  useAuthReady,
  type SessionAuthData,
} from './auth';

const fakeUser = { id: 'u1', email: 'alice@example.com' };
const fakeOrg = { id: 'o1', name: 'Acme' };
const fakePayload: SessionAuthData = { user: fakeUser, org: fakeOrg };

function makeResponse(status: number, body?: unknown): Response {
  return new Response(body !== undefined ? JSON.stringify(body) : null, {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('useSessionAuthInit', () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchSpy = vi.fn();
    globalThis.fetch = fetchSpy as unknown as typeof fetch;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('200 from /api/auth/me → setUser(user) + setInitialized + auth-ready', async () => {
    fetchSpy.mockResolvedValueOnce(makeResponse(200, fakePayload));
    const setUser = vi.fn();
    const setInitialized = vi.fn();

    renderHook(() => useSessionAuthInit(setUser, setInitialized));

    await waitFor(() => expect(setUser).toHaveBeenCalled());

    expect(setUser).toHaveBeenCalledWith(fakeUser);
    expect(setInitialized).toHaveBeenCalledTimes(1);
    expect(fetchSpy).toHaveBeenCalledWith('/api/auth/me', expect.objectContaining({
      method: 'GET',
      credentials: 'include',
    }));

    // useAuthReady should flip to true after the init resolves.
    const { result } = renderHook(() => useAuthReady());
    await waitFor(() => expect(result.current).toBe(true));
  });

  it('401 from /api/auth/me → setUser(null) + setInitialized + auth-ready', async () => {
    fetchSpy.mockResolvedValueOnce(makeResponse(401, { detail: 'auth required' }));
    const setUser = vi.fn();
    const setInitialized = vi.fn();

    renderHook(() => useSessionAuthInit(setUser, setInitialized));

    await waitFor(() => expect(setUser).toHaveBeenCalled());
    expect(setUser).toHaveBeenCalledWith(null);
    expect(setInitialized).toHaveBeenCalledTimes(1);
  });

  it('network failure → setUser(null) + still resolves init/ready (no spinner forever)', async () => {
    fetchSpy.mockRejectedValueOnce(new TypeError('network down'));
    const setUser = vi.fn();
    const setInitialized = vi.fn();

    renderHook(() => useSessionAuthInit(setUser, setInitialized));

    await waitFor(() => expect(setInitialized).toHaveBeenCalled());
    expect(setUser).toHaveBeenCalledWith(null);
  });

  it('setInitialized is optional — boot completes without it', async () => {
    fetchSpy.mockResolvedValueOnce(makeResponse(200, fakePayload));
    const setUser = vi.fn();

    renderHook(() => useSessionAuthInit(setUser));

    await waitFor(() => expect(setUser).toHaveBeenCalledWith(fakeUser));
    // No throw on missing setInitialized.
  });
});

describe('loginWithSession', () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchSpy = vi.fn();
    globalThis.fetch = fetchSpy as unknown as typeof fetch;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('200 → returns the {user, org} payload', async () => {
    fetchSpy.mockResolvedValueOnce(makeResponse(200, fakePayload));

    const data = await loginWithSession({ email: 'alice@example.com', password: 'pw12345' });

    expect(data).toEqual(fakePayload);
    expect(fetchSpy).toHaveBeenCalledWith('/api/auth/login', expect.objectContaining({
      method: 'POST',
      credentials: 'include',
      body: JSON.stringify({ email: 'alice@example.com', password: 'pw12345' }),
    }));
  });

  it('401 with detail → throws with the server-supplied detail', async () => {
    fetchSpy.mockResolvedValueOnce(makeResponse(401, { detail: 'invalid credentials' }));

    await expect(
      loginWithSession({ email: 'alice@example.com', password: 'wrong' }),
    ).rejects.toThrow('invalid credentials');
  });

  it('non-JSON error body → throws with a default message', async () => {
    fetchSpy.mockResolvedValueOnce(new Response('not json', { status: 500 }));

    await expect(
      loginWithSession({ email: 'a@b.co', password: 'x' }),
    ).rejects.toThrow();
  });
});

describe('logoutSession', () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchSpy = vi.fn();
    globalThis.fetch = fetchSpy as unknown as typeof fetch;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('204 → resolves', async () => {
    fetchSpy.mockResolvedValueOnce(new Response(null, { status: 204 }));

    await expect(logoutSession()).resolves.toBeUndefined();
    expect(fetchSpy).toHaveBeenCalledWith('/api/auth/logout', expect.objectContaining({
      method: 'POST',
      credentials: 'include',
    }));
  });

  it('500 → throws', async () => {
    fetchSpy.mockResolvedValueOnce(new Response(null, { status: 500 }));

    await expect(logoutSession()).rejects.toThrow(/logout failed/);
  });
});

describe('useAuthReady regression', () => {
  it('flips to true after useSessionAuthInit resolves', async () => {
    const fetchSpy = vi.fn().mockResolvedValueOnce(makeResponse(401));
    globalThis.fetch = fetchSpy as unknown as typeof fetch;

    const ready = renderHook(() => useAuthReady());
    const init = renderHook(() => useSessionAuthInit(vi.fn()));

    await waitFor(() => expect(ready.result.current).toBe(true));

    // Force unmount.
    act(() => {
      init.unmount();
    });
  });
});
