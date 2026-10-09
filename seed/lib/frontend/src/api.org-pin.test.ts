import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { createApiClient } from './api';
import { ORG_PIN_HEADER, orgPinFetch, setOrgPin, setOrgSelectionChangedHandler } from './org-pin';

const json = (status: number, body: unknown = {}) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

const make = () => createApiClient({ getBaseUrl: () => 'http://x', getAuthToken: async () => 'tok' });

describe('api org pin', () => {
  beforeEach(() => { vi.restoreAllMocks(); setOrgPin(null); setOrgSelectionChangedHandler(null); });
  afterEach(() => { vi.restoreAllMocks(); setOrgPin(null); setOrgSelectionChangedHandler(null); });

  it('sends X-Noctus-Acting-Org only when pinned', async () => {
    const f = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => json(200, {}));
    await make().get('/api/a');
    expect((f.mock.calls[0][1] as any).headers[ORG_PIN_HEADER]).toBeUndefined();
    setOrgPin('o1');
    await make().get('/api/a');
    expect((f.mock.calls[1][1] as any).headers[ORG_PIN_HEADER]).toBe('o1');
  });

  it('409 org_selection_changed clears the pin and fires the handler once (no loop)', async () => {
    const handler = vi.fn();
    setOrgSelectionChangedHandler(handler);
    setOrgPin('o1');
    const f = vi.spyOn(globalThis, 'fetch').mockImplementation(async () =>
      json(409, { detail: { code: 'org_selection_changed' } }));
    const c = make();
    await expect(c.get('/api/a')).rejects.toThrow('[409]');
    expect(handler).toHaveBeenCalledTimes(1);
    expect(f).toHaveBeenCalledTimes(1); // no automatic retry
    // the stale pin is gone: the next request no longer carries it
    await expect(c.get('/api/a')).rejects.toThrow();
    expect((f.mock.calls[1][1] as any).headers[ORG_PIN_HEADER]).toBeUndefined();
  });

  it('other 409s do not fire the handler', async () => {
    const handler = vi.fn();
    setOrgSelectionChangedHandler(handler);
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => json(409, { detail: 'conflito' }));
    await expect(make().get('/api/a')).rejects.toThrow('[409]');
    expect(handler).not.toHaveBeenCalled();
  });

  it('orgPinFetch (Supabase client) adds the header when pinned', async () => {
    const f = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => json(200, {}));
    await orgPinFetch('http://s/rest/v1/x', { headers: { apikey: 'k' } });
    expect(new Headers((f.mock.calls[0][1] as any).headers).has(ORG_PIN_HEADER)).toBe(false);
    setOrgPin('o9');
    await orgPinFetch('http://s/rest/v1/x', { headers: { apikey: 'k' } });
    const h = new Headers((f.mock.calls[1][1] as any).headers);
    expect(h.get(ORG_PIN_HEADER)).toBe('o9');
    expect(h.get('apikey')).toBe('k');
  });
});
