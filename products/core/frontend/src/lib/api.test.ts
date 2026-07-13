/**
 * Tests for core's wiring of the shared `createApiClient` dead-session seam
 * (`onTokenExpired` / `onUnauthenticated`). Core previously left both hooks
 * unwired, so an expired core session fell through to a blocking native
 * `alert("[401] ...")` on every failed call instead of the seed's documented
 * "refresh-once, then redirect to /login" behavior.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

function jsonResponse(status: number, body: unknown = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('core api client — dead-session seam wiring', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    // `_handlingDeadSession` is module-scoped state in lib/api.ts (mirrors the
    // seed's own `infra.tsx`) — reset the module graph per test so the guard
    // doesn't leak across tests (it only self-clears after a real 3s timeout).
    vi.resetModules();
    localStorage.clear();
    Object.defineProperty(window, 'location', {
      value: { assign: vi.fn(), pathname: '/', origin: 'http://localhost:3000' },
      writable: true,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it('refreshes the access token and retries once on a recoverable 401', async () => {
    localStorage.setItem('noctus_token', 'old-token');
    localStorage.setItem('noctus_refresh_token', 'old-refresh');

    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse(401, { detail: 'expired' })) // original call
      .mockResolvedValueOnce(
        jsonResponse(200, { access_token: 'new-token', refresh_token: 'new-refresh' }),
      ) // POST /api/auth/refresh
      .mockResolvedValueOnce(jsonResponse(200, { ok: true })); // retried call

    const { api } = await import('./api');
    await expect(api.get('/api/x')).resolves.toEqual({ ok: true });

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[1][0]).toContain('/api/auth/refresh');
    expect(localStorage.getItem('noctus_token')).toBe('new-token');
    expect(localStorage.getItem('noctus_refresh_token')).toBe('new-refresh');
    expect((window.location.assign as any)).not.toHaveBeenCalled();
  });

  it('clears tokens and redirects to /login when there is no refresh token to try', async () => {
    localStorage.setItem('noctus_token', 'old-token');
    // no noctus_refresh_token stored

    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(401, { detail: 'Token ausente' }));

    const { api } = await import('./api');
    await expect(api.get('/api/x')).rejects.toThrow('[401]');

    expect(localStorage.getItem('noctus_token')).toBeNull();
    expect(localStorage.getItem('noctus_refresh_token')).toBeNull();
    expect(window.location.assign).toHaveBeenCalledWith('/login');
  });

  it('clears tokens and redirects to /login when the refreshed token STILL 401s', async () => {
    localStorage.setItem('noctus_token', 'old-token');
    localStorage.setItem('noctus_refresh_token', 'stale-refresh');

    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse(401, { detail: 'expired' })) // original call
      .mockResolvedValueOnce(jsonResponse(200, { access_token: 'new-token' })) // refresh "succeeds"
      .mockResolvedValueOnce(jsonResponse(401, { detail: 'Token invalido' })); // retry STILL 401s

    const { api } = await import('./api');
    await expect(api.get('/api/x')).rejects.toThrow('[401]');

    expect(localStorage.getItem('noctus_token')).toBeNull();
    expect(window.location.assign).toHaveBeenCalledWith('/login');
  });

  it('does NOT redirect while already on /login (no loop)', async () => {
    Object.defineProperty(window, 'location', {
      value: { assign: vi.fn(), pathname: '/login', origin: 'http://localhost:3000' },
      writable: true,
    });
    localStorage.setItem('noctus_token', 'old-token');

    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(401, { detail: 'Token ausente' }));

    const { api } = await import('./api');
    await expect(api.get('/api/x')).rejects.toThrow('[401]');

    expect(window.location.assign).not.toHaveBeenCalled();
  });
});
