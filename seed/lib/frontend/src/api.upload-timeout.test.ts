/**
 * `api.upload` must REJECT when the server never answers (backend restart,
 * edge 530 holding the socket) — otherwise the caller's `isPending` ("Enviando
 * anexo…") is pinned forever. A 5xx/530 must surface as an ApiError too.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError, UPLOAD_TIMEOUT_MS, createApiClient } from './api';

const client = () =>
  createApiClient({ getBaseUrl: () => 'http://api.test', getAuthToken: async () => 'tok' });

describe('api.upload failure modes', () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

  it('aborts a hung POST after UPLOAD_TIMEOUT_MS and rejects with ApiError', async () => {
    vi.stubGlobal('fetch', vi.fn((_u: string, init: RequestInit) => new Promise((_res, rej) => {
      init.signal!.addEventListener('abort', () => rej(new DOMException('aborted', 'AbortError')));
    })));
    const p = client().upload('/api/x', new FormData());
    const assertion = expect(p).rejects.toBeInstanceOf(ApiError);
    await vi.advanceTimersByTimeAsync(UPLOAD_TIMEOUT_MS + 1);
    await assertion;
    await expect(p).rejects.toMatchObject({ status: null, message: expect.stringContaining('demorou demais') });
  });

  it('a 530 response rejects with its status', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('error code: 1033', { status: 530 })));
    await expect(client().upload('/api/x', new FormData())).rejects.toMatchObject({ status: 530 });
  });

  it('a normal upload resolves and clears the timer', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ ok: 1 }), { status: 200 })));
    await expect(client().upload('/api/x', new FormData())).resolves.toEqual({ ok: 1 });
    expect(vi.getTimerCount()).toBe(0);
  });
});
