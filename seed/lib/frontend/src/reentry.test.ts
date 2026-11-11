import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  INFLIGHT_TTL_MS,
  LOOP_MAX_TRIPS,
  LOOP_WINDOW_MS,
  REENTRY_INFLIGHT_KEY,
  REENTRY_TRIPS_KEY,
  applyLoginRequiredBounce,
  buildCoreEntryUrl,
  decideEntry,
  enterViaCore,
  isLoginRequiredBounce,
  isLoopTripped,
  readEntryMarker,
  sanitizeNextPath,
  whenVisible,
  type EntryMarker,
} from './reentry';

const CORE = 'https://noctusai.com';

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
});

describe('decision table (design record D)', () => {
  const none: EntryMarker | null = null;
  it.each<[string, Parameters<typeof decideEntry>[0], unknown]>([
    ['fresh, protected path, no marker', { phase: 'fresh', pathname: '/clientes/1', marker: none }, { kind: 'core', prompt: 'login' }],
    ['fresh, protected path, signed-out', { phase: 'fresh', pathname: '/clientes/1', marker: 'signed-out' }, { kind: 'core', prompt: 'login' }],
    ['fresh, protected path, active', { phase: 'fresh', pathname: '/x', marker: 'active' }, { kind: 'core', prompt: 'login' }],
    ['fresh, "/", marker absent', { phase: 'fresh', pathname: '/', marker: none }, { kind: 'landing' }],
    ['fresh, "/", signed-out', { phase: 'fresh', pathname: '/', marker: 'signed-out' }, { kind: 'landing' }],
    ['fresh, "/", left', { phase: 'fresh', pathname: '/', marker: 'left' }, { kind: 'core', prompt: 'none' }],
    ['fresh, "/", active', { phase: 'fresh', pathname: '/', marker: 'active' }, { kind: 'core', prompt: 'none' }],
    ['lost, left, protected path', { phase: 'lost', pathname: '/clientes/1', marker: 'left' }, { kind: 'core', prompt: 'login' }],
    ['lost, active, protected path', { phase: 'lost', pathname: '/clientes/1', marker: 'active' }, { kind: 'core', prompt: 'login' }],
    ['lost, active, "/"', { phase: 'lost', pathname: '/', marker: 'active' }, { kind: 'core', prompt: 'login' }],
    ['lost, signed-out, protected path', { phase: 'lost', pathname: '/clientes/1', marker: 'signed-out' }, { kind: 'product-landing' }],
    ['lost, signed-out, "/"', { phase: 'lost', pathname: '/', marker: 'signed-out' }, { kind: 'landing' }],
  ])('%s', (_name, input, expected) => {
    expect(decideEntry(input)).toEqual(expected);
  });
});

describe('marker', () => {
  it('only accepts active|left|signed-out', () => {
    expect(readEntryMarker()).toBeNull();
    localStorage.setItem('noctus:entry', 'bogus');
    expect(readEntryMarker()).toBeNull();
    localStorage.setItem('noctus:entry', 'left');
    expect(readEntryMarker()).toBe('left');
  });
});

describe('core URL', () => {
  it('uses the slug and a path-only next, on the core origin', () => {
    expect(buildCoreEntryUrl({ coreUrl: `${CORE}/`, slug: 'agents', next: '/a/b?x=1', prompt: 'login' })).toBe(
      `${CORE}/login?produto=agents&next=%2Fa%2Fb%3Fx%3D1&prompt=login`,
    );
  });
  it('omits next for "/" and for anything that is not a path', () => {
    expect(buildCoreEntryUrl({ coreUrl: CORE, slug: 'agents', next: '/', prompt: 'none' })).toBe(`${CORE}/login?produto=agents&prompt=none`);
    for (const bad of ['//evil.example', 'https://evil.example', '/a\\b', '/a\nb', '', null, undefined]) {
      expect(sanitizeNextPath(bad as string | null | undefined)).toBeNull();
    }
  });
  it('targets /esqueci-senha for the password reset', () => {
    expect(buildCoreEntryUrl({ coreUrl: CORE, slug: 'agents', next: '/x', route: '/esqueci-senha' })).toBe(
      `${CORE}/esqueci-senha?produto=agents&next=%2Fx`,
    );
  });
});

describe('#sso=login_required', () => {
  it('recognises the fragment and stamps signed-out, clearing the inflight stamp', () => {
    localStorage.setItem('noctus:entry', 'left');
    localStorage.setItem(REENTRY_INFLIGHT_KEY, String(Date.now()));
    expect(isLoginRequiredBounce('#sso=login_required')).toBe(true);
    expect(isLoginRequiredBounce('#sso=other')).toBe(false);
    expect(applyLoginRequiredBounce('#sso=login_required')).toBe(true);
    expect(readEntryMarker()).toBe('signed-out');
    expect(localStorage.getItem(REENTRY_INFLIGHT_KEY)).toBeNull();
  });
  it('does nothing for any other fragment', () => {
    localStorage.setItem('noctus:entry', 'left');
    expect(applyLoginRequiredBounce('#foo=bar')).toBe(false);
    expect(readEntryMarker()).toBe('left');
  });
});

/** A tiny Web Locks stand-in: `ifAvailable` grants the lock only when nobody holds it. */
function fakeLocks() {
  const held = new Set<string>();
  const request = vi.fn(async (name: string, _opts: unknown, cb: (lock: unknown) => Promise<unknown>) => {
    if (held.has(name)) return cb(null);
    held.add(name);
    try {
      return await cb({ name });
    } finally {
      held.delete(name);
    }
  });
  return { request, locks: { request } as unknown as Pick<LockManager, 'request'> };
}

const visible = { visibilityState: 'visible' } as const;
const hidden = { visibilityState: 'hidden' } as const;

describe('enterViaCore', () => {
  it('a hidden tab never navigates', async () => {
    const navigate = vi.fn();
    const out = await enterViaCore('u', 'agents', { doc: hidden, navigate, locks: fakeLocks().locks });
    expect(out).toEqual({ status: 'hidden' });
    expect(navigate).not.toHaveBeenCalled();
    expect(localStorage.getItem(REENTRY_INFLIGHT_KEY)).toBeNull();
  });

  it('the lock yields ONE navigation for N visible tabs', async () => {
    const { locks } = fakeLocks();
    const navigate = vi.fn();
    const outs = await Promise.all(Array.from({ length: 5 }, () => enterViaCore('u', 'agents', { doc: visible, navigate, locks })));
    expect(navigate).toHaveBeenCalledTimes(1);
    expect(outs.filter((o) => o.status === 'navigated')).toHaveLength(1);
    expect(outs.filter((o) => o.status === 'deferred')).toHaveLength(4);
  });

  it('the 60 s inflight stamp stops a second window that arrives after the lock was released', async () => {
    const navigate = vi.fn();
    let t = 1_000_000;
    const deps = { doc: visible, navigate, locks: fakeLocks().locks, now: () => t };
    expect((await enterViaCore('u', 'agents', deps)).status).toBe('navigated');
    t += 5_000;
    expect(await enterViaCore('u', 'agents', deps)).toEqual({ status: 'deferred', retryInMs: INFLIGHT_TTL_MS - 5_000 });
    expect(navigate).toHaveBeenCalledTimes(1);
    t += INFLIGHT_TTL_MS;
    expect((await enterViaCore('u', 'agents', deps)).status).toBe('navigated');
    expect(navigate).toHaveBeenCalledTimes(2);
  });

  it('serialises per slug only', async () => {
    const navigate = vi.fn();
    const { locks, request } = fakeLocks();
    await enterViaCore('u1', 'agents', { doc: visible, navigate, locks });
    await enterViaCore('u2', 'nosnolimiar', { doc: visible, navigate, locks });
    expect(request.mock.calls.map((c) => c[0])).toEqual(['noctus-reentry:agents', 'noctus-reentry:nosnolimiar']);
  });

  it('still works (inflight stamp only) where Web Locks do not exist', async () => {
    const navigate = vi.fn();
    const out = await enterViaCore('u', 'agents', { doc: visible, navigate, locks: null });
    expect(out.status).toBe('navigated');
  });

  it('loop guard: stops after 3 round trips in 2 min without a redeem', async () => {
    const navigate = vi.fn();
    let t = 5_000_000;
    const run = () => {
      localStorage.removeItem(REENTRY_INFLIGHT_KEY); // each bounce closed the previous trip's inflight stamp
      return enterViaCore('u', 'agents', { doc: visible, navigate, locks: null, now: () => t });
    };
    for (let i = 0; i < LOOP_MAX_TRIPS; i++) {
      expect((await run()).status).toBe('navigated');
      t += 10_000;
    }
    expect(isLoopTripped(sessionStorage, t)).toBe(true);
    expect(await run()).toEqual({ status: 'loop' });
    expect(navigate).toHaveBeenCalledTimes(LOOP_MAX_TRIPS);
  });

  it('loop guard: trips older than 2 min do not count', () => {
    const t = 9_000_000;
    sessionStorage.setItem(REENTRY_TRIPS_KEY, JSON.stringify([t - LOOP_WINDOW_MS - 1, t - LOOP_WINDOW_MS - 2, t - LOOP_WINDOW_MS - 3]));
    expect(isLoopTripped(sessionStorage, t)).toBe(false);
  });
});

describe('whenVisible', () => {
  it('resolves on the visibilitychange to visible, and cancel() abandons the wait', async () => {
    const listeners = new Set<() => void>();
    const doc = {
      visibilityState: 'hidden' as DocumentVisibilityState,
      addEventListener: (_: string, l: () => void) => listeners.add(l),
      removeEventListener: (_: string, l: () => void) => listeners.delete(l),
    };
    const w = whenVisible(doc as unknown as Document);
    doc.visibilityState = 'visible';
    listeners.forEach((l) => l());
    expect(await w.promise).toBe(true);
    expect(listeners.size).toBe(0);

    doc.visibilityState = 'hidden';
    const w2 = whenVisible(doc as unknown as Document);
    w2.cancel();
    expect(await w2.promise).toBe(false);
    expect(listeners.size).toBe(0);
  });
});
