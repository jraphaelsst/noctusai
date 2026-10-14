/** `post(path, body, { headers })` — extra request headers (e.g. `Idempotency-Key`) that never displace auth. */
import { describe, it, expect, afterEach, vi } from 'vitest';
import { createApiClient } from './api';

afterEach(() => vi.restoreAllMocks());

function make() {
  const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response('{"data":1}', { status: 200, headers: { 'Content-Type': 'application/json' } }),
  );
  const client = createApiClient({ getBaseUrl: () => 'http://x', getAuthToken: async () => 'tok' });
  return { client, fetchSpy };
}

describe('createApiClient.post options.headers', () => {
  it('sends the extra header alongside the auth header', async () => {
    const { client, fetchSpy } = make();
    await client.post('/p', { a: 1 }, { headers: { 'Idempotency-Key': 'k1' } });
    const headers = fetchSpy.mock.calls[0][1]!.headers as Record<string, string>;
    expect(headers['Idempotency-Key']).toBe('k1');
    expect(headers['Authorization']).toBe('Bearer tok');
  });

  it('can never override the auth header', async () => {
    const { client, fetchSpy } = make();
    await client.post('/p', {}, { headers: { Authorization: 'Bearer evil' } });
    expect((fetchSpy.mock.calls[0][1]!.headers as Record<string, string>)['Authorization']).toBe('Bearer tok');
  });

  it('without options behaves as before', async () => {
    const { client, fetchSpy } = make();
    await client.post('/p', { a: 1 });
    expect((fetchSpy.mock.calls[0][1]!.headers as Record<string, string>)['Idempotency-Key']).toBeUndefined();
  });
});
