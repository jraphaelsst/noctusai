/// <reference types="@testing-library/jest-dom" />
/**
 * Tests for createApiClient's dead-session handling (`onUnauthenticated`).
 *
 * The 2026-07-03 report: an expired session left the user on a logged-in shell
 * that 401'd every call ("[401] Token ausente" on every page). The client now
 * signals `onUnauthenticated` on an UNRECOVERABLE 401 so the product bounces to
 * login — but NEVER on a recoverable 401 (refresh succeeded), a 403 (permission),
 * or a 2xx.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

import { createApiClient, type CreateApiClientOptions } from './api';

function jsonResponse(status: number, body: unknown = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function make(opts: Partial<CreateApiClientOptions> = {}) {
  const onUnauthenticated = vi.fn();
  const client = createApiClient({
    getBaseUrl: () => 'http://x',
    getAuthToken: async () => 'tok',
    onUnauthenticated,
    ...opts,
  });
  return { client, onUnauthenticated };
}

describe('createApiClient — onUnauthenticated on a dead session', () => {
  beforeEach(() => vi.restoreAllMocks());
  afterEach(() => vi.restoreAllMocks());

  it('fires on a 401 with no refresh configured (unrecoverable)', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(401, { detail: 'Token ausente' }));
    const { client, onUnauthenticated } = make();
    await expect(client.get('/api/x')).rejects.toThrow('[401]');
    expect(onUnauthenticated).toHaveBeenCalledTimes(1);
  });

  it('fires when refresh returns null (session cannot be restored)', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(401, { detail: 'Token ausente' }));
    const { client, onUnauthenticated } = make({ onTokenExpired: async () => null });
    await expect(client.get('/api/x')).rejects.toThrow('[401]');
    expect(onUnauthenticated).toHaveBeenCalledTimes(1);
  });

  it('fires when the refreshed token STILL 401s', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(401, { detail: 'Token invalido' }));
    const { client, onUnauthenticated } = make({ onTokenExpired: async () => 'fresh' });
    await expect(client.get('/api/x')).rejects.toThrow('[401]');
    expect(onUnauthenticated).toHaveBeenCalledTimes(1);
  });

  it('does NOT fire when refresh recovers the request', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse(401, { detail: 'expired' })) // first attempt 401
      .mockResolvedValueOnce(jsonResponse(200, { ok: true }));         // retry with fresh token 200
    const { client, onUnauthenticated } = make({ onTokenExpired: async () => 'fresh' });
    await expect(client.get('/api/x')).resolves.toEqual({ ok: true });
    expect(onUnauthenticated).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('does NOT fire on a successful request', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(200, { ok: true }));
    const { client, onUnauthenticated } = make();
    await client.get('/api/x');
    expect(onUnauthenticated).not.toHaveBeenCalled();
  });

  it('does NOT fire on a 403 (permission denied, not a dead session)', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(403, { detail: 'forbidden' }));
    const { client, onUnauthenticated } = make();
    await expect(client.get('/api/x')).rejects.toThrow('[403]');
    expect(onUnauthenticated).not.toHaveBeenCalled();
  });

  it('is optional — a client without the callback still throws the 401 normally', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(401, { detail: 'Token ausente' }));
    const client = createApiClient({ getBaseUrl: () => 'http://x', getAuthToken: async () => null });
    await expect(client.get('/api/x')).rejects.toThrow('[401]');  // no throw from a missing callback
  });
});
