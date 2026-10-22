import { describe, it, expect, vi } from 'vitest';
import { dropProductCookieSession } from './identity';

describe('dropProductCookieSession', () => {
  it('sends X-Keep-Session when the SPA session id is given', async () => {
    const f = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    globalThis.fetch = f as unknown as typeof fetch;
    await dropProductCookieSession('sid-1');
    expect(f.mock.calls[0][1].headers).toEqual({ 'X-Keep-Session': 'sid-1' });
    await dropProductCookieSession();
    expect(f.mock.calls[1][1].headers).toBeUndefined();
  });
});
