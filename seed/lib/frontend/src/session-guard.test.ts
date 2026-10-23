/**
 * The browser is the ONE owner of the shared GoTrue refresh-token chain; a
 * refresh refused for a token another tab already rotated must never delete
 * that tab's live pair (prod 2026-10-23 17:22: `refresh_token_already_used`
 * from one tab wiped the slot and every tab fell to Landing).
 */
import { describe, expect, it, vi } from 'vitest';
import { createRefreshOwnershipGuard, type GuardableStorage } from './session-guard';

const KEY = 'sb-ref-auth-token';
const REFRESH_URL = 'https://ref.supabase.co/auth/v1/token?grant_type=refresh_token';

function memoryStorage(): GuardableStorage & { data: Map<string, string> } {
  const data = new Map<string, string>();
  return {
    data,
    getItem: (k) => data.get(k) ?? null,
    setItem: (k, v) => void data.set(k, v),
    removeItem: (k) => void data.delete(k),
  };
}

const session = (rt: string) => JSON.stringify({ access_token: `at-${rt}`, refresh_token: rt });

function setup(status: number) {
  const base = memoryStorage();
  const baseFetch = vi.fn(async () => new Response('{}', { status }));
  const guard = createRefreshOwnershipGuard(baseFetch, base);
  const refresh = (rt: string) =>
    guard.fetch(REFRESH_URL, { method: 'POST', body: JSON.stringify({ refresh_token: rt }) });
  return { base, guard, refresh, baseFetch };
}

describe('createRefreshOwnershipGuard', () => {
  it('a refusal of a SUPERSEDED token never removes the rotated pair another tab stored', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const { base, guard, refresh } = setup(400);
    base.setItem(KEY, session('rt-1'));
    // this tab presents rt-1 ...
    const pending = refresh('rt-1');
    // ... while another tab rotates the shared slot to rt-2
    base.setItem(KEY, session('rt-2'));
    await pending;
    guard.storage.removeItem(KEY); // supabase-js _removeSession after the 400
    expect(base.getItem(KEY)).toBe(session('rt-2'));
    expect(warn).toHaveBeenCalledTimes(1);
    warn.mockRestore();
  });

  it('a refusal of the token the slot still holds is a dead chain: removal honoured', async () => {
    const { base, guard, refresh } = setup(400);
    base.setItem(KEY, session('rt-1'));
    await refresh('rt-1');
    guard.storage.removeItem(KEY);
    expect(base.getItem(KEY)).toBeNull();
  });

  it('an explicit sign-out (no refused refresh) always removes', () => {
    const { base, guard } = setup(200);
    base.setItem(KEY, session('rt-9'));
    guard.storage.removeItem(KEY);
    expect(base.getItem(KEY)).toBeNull();
  });

  it('the refusal record is one-shot: a later sign-out of the rotated pair is honoured', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const { base, guard, refresh } = setup(400);
    base.setItem(KEY, session('rt-1'));
    await refresh('rt-1');
    base.setItem(KEY, session('rt-2'));
    guard.storage.removeItem(KEY); // refused: rt-2 is live
    guard.storage.removeItem(KEY); // the user signs out
    expect(base.getItem(KEY)).toBeNull();
    warn.mockRestore();
  });

  it('a successful or unanswered refresh clears the refusal record', async () => {
    const base = memoryStorage();
    const statuses = [400, 200];
    const guard = createRefreshOwnershipGuard(async () => new Response('{}', { status: statuses.shift() }), base);
    const body = (rt: string) => ({ method: 'POST', body: JSON.stringify({ refresh_token: rt }) });
    await guard.fetch(REFRESH_URL, body('rt-1'));
    await guard.fetch(REFRESH_URL, body('rt-1'));
    base.setItem(KEY, session('rt-2'));
    guard.storage.removeItem(KEY);
    expect(base.getItem(KEY)).toBeNull();
  });

  it('side keys (code verifier, user) are never guarded', async () => {
    const { base, guard, refresh } = setup(400);
    base.setItem(KEY, session('rt-2'));
    base.setItem(`${KEY}-user`, JSON.stringify({ user: { id: 'u' } }));
    await refresh('rt-1');
    guard.storage.removeItem(`${KEY}-user`);
    expect(base.getItem(`${KEY}-user`)).toBeNull();
  });

  it('non-refresh requests pass through untouched', async () => {
    const { guard, baseFetch } = setup(401);
    await guard.fetch('https://ref.supabase.co/rest/v1/x', { method: 'GET' });
    expect(baseFetch).toHaveBeenCalledTimes(1);
  });
});
