import { renderHook, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const apiGet = vi.fn();
vi.mock('@noctusai/seed/infra', () => ({
  supabase: { removeAllChannels: async () => [] },
  api: { get: (...a: unknown[]) => apiGet(...a), put: vi.fn(), delete: vi.fn() },
}));

import { useOrgSelection, resetOrgSelectionPage, ME_ACCESS_QUERY_KEY } from './org-selection';
import { getOrgPin, setOrgPin, notifyOrgSelectionChanged } from './org-pin';
import { markOrgVisit } from './org-visit';

const X = { id: 'x', nome: 'X' };
const Y = { id: 'y', nome: 'Y' };
const access = (org: { id: string; nome: string }) => ({
  has_access: true, product_slug: 'p', org,
  org_selection: {
    available: true, required: false, mfa_required: false, acting: true,
    org, home_org: X, selection_id: `sel-${org.id}`,
  },
});

describe('useOrgSelection pin vs org swap', () => {
  const reload = vi.fn();
  const orig = window.location;
  let qc: QueryClient;
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  beforeEach(() => {
    apiGet.mockReset(); reload.mockReset();
    resetOrgSelectionPage(); setOrgPin(null);
    // These cover reloads WITHIN a visit (the tab already chose): marker present.
    markOrgVisit('x');
    qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    Object.defineProperty(window, 'location', { configurable: true, value: { ...orig, reload } });
  });
  afterEach(() => {
    cleanup();
    window.sessionStorage.clear();
    Object.defineProperty(window, 'location', { configurable: true, value: orig });
  });

  it('first access pins without reload', async () => {
    apiGet.mockResolvedValue(access(X));
    renderHook(() => useOrgSelection(), { wrapper });
    await waitFor(() => expect(getOrgPin()).toBe('x'));
    expect(reload).not.toHaveBeenCalled();
  });

  it('access reporting another org under an existing pin reloads, never re-pins', async () => {
    apiGet.mockResolvedValue(access(X));
    renderHook(() => useOrgSelection(), { wrapper });
    await waitFor(() => expect(getOrgPin()).toBe('x'));
    apiGet.mockResolvedValue(access(Y));
    await qc.invalidateQueries({ queryKey: ME_ACCESS_QUERY_KEY });
    await waitFor(() => expect(reload).toHaveBeenCalledTimes(1));
    expect(getOrgPin()).toBe('x');
  });

  it('after a 409 pin-clear, a refetch reporting another org reloads instead of silently re-pinning', async () => {
    apiGet.mockResolvedValue(access(X));
    renderHook(() => useOrgSelection(), { wrapper });
    await waitFor(() => expect(getOrgPin()).toBe('x'));
    notifyOrgSelectionChanged();
    expect(getOrgPin()).toBeNull();
    apiGet.mockResolvedValue(access(Y));
    await qc.invalidateQueries({ queryKey: ME_ACCESS_QUERY_KEY });
    await waitFor(() => expect(reload).toHaveBeenCalledTimes(1));
    expect(getOrgPin()).not.toBe('y');
  });

  it('same-org refetch does not reload (and restores the pin after a 409 clear)', async () => {
    apiGet.mockResolvedValue(access(X));
    renderHook(() => useOrgSelection(), { wrapper });
    await waitFor(() => expect(getOrgPin()).toBe('x'));
    notifyOrgSelectionChanged();
    await qc.invalidateQueries({ queryKey: ME_ACCESS_QUERY_KEY });
    await waitFor(() => expect(getOrgPin()).toBe('x'));
    expect(reload).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Shell access waterfall: the first entry of a tab renders while access revalidates
// ONLY when a per-user "no picker" hint exists.
// ---------------------------------------------------------------------------
import {
  clearOrgAccessHint, hasOrgAccessHint, resetOrgAccessHint, setOrgHintUser, writeOrgAccessHint,
  ORG_ACCESS_HINT_TTL_MS,
} from './org-access-hint';
import { endOrgSelectionBestEffort } from './org-selection';

const solo = { has_access: true, product_slug: 'p', org: X, org_selection: undefined };
const picker = (required: boolean) => ({
  has_access: true, product_slug: 'p', org: X,
  org_selection: {
    available: true, required, mfa_required: false, acting: false,
    org: X, home_org: X, selection_id: null, manage_any_org: true,
  },
});

const memStore = (): Storage => {
  const m = new Map<string, string>();
  return {
    get length() { return m.size; }, clear: () => m.clear(), key: (i: number) => [...m.keys()][i] ?? null,
    getItem: (k: string) => m.get(k) ?? null, removeItem: (k: string) => { m.delete(k); },
    setItem: (k: string, v: string) => { m.set(k, String(v)); },
  };
};

describe('useOrgSelection early render from the no-picker hint', () => {
  const realLocal = Object.getOwnPropertyDescriptor(window, 'localStorage');
  let qc: QueryClient;
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  const pending = () => new Promise(() => {});
  beforeEach(() => {
    apiGet.mockReset();
    resetOrgSelectionPage(); setOrgPin(null);
    Object.defineProperty(window, 'localStorage', { configurable: true, value: memStore() });
    window.sessionStorage.clear(); resetOrgAccessHint();
    qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  });
  afterEach(() => { cleanup(); window.sessionStorage.clear(); resetOrgAccessHint();
    if (realLocal) Object.defineProperty(window, 'localStorage', realLocal);
  });

  it('no hint: an entry stays blocked while access is pending (unchanged)', () => {
    apiGet.mockReturnValue(pending());
    const { result } = renderHook(() => useOrgSelection(), { wrapper });
    expect(result.current.contentBlocked).toBe(true);
  });

  it('hint for the current user: entry renders at once, access still pending', () => {
    setOrgHintUser('u1'); writeOrgAccessHint();
    apiGet.mockReturnValue(pending());
    const { result } = renderHook(() => useOrgSelection(), { wrapper });
    expect(result.current.contentBlocked).toBe(false);
    expect(result.current.showSkeleton).toBe(true);
  });

  it('hint is never reused by another user (and is dropped)', () => {
    setOrgHintUser('u1'); writeOrgAccessHint();
    setOrgHintUser('u2');
    expect(hasOrgAccessHint()).toBe(false);
    setOrgHintUser('u1');
    expect(hasOrgAccessHint()).toBe(false); // gone, not parked
  });

  it('hint for an unknown user is ignored', () => {
    setOrgHintUser('u1'); writeOrgAccessHint();
    setOrgHintUser(null);
    expect(hasOrgAccessHint()).toBe(false);
  });

  it('an expired hint is ignored', () => {
    setOrgHintUser('u1'); writeOrgAccessHint();
    const now = Date.now();
    const spy = vi.spyOn(Date, 'now').mockReturnValue(now + ORG_ACCESS_HINT_TTL_MS + 1);
    expect(hasOrgAccessHint()).toBe(false);
    spy.mockRestore();
  });

  it('unavailable storage reads as no hint', () => {
    setOrgHintUser('u1');
    const spy = vi.spyOn(window.localStorage, 'getItem').mockImplementation(() => { throw new Error('denied'); });
    expect(hasOrgAccessHint()).toBe(false);
    spy.mockRestore();
  });

  it('contradiction (staff, first entry): content re-blocks and the hint is dropped', async () => {
    setOrgHintUser('u1'); writeOrgAccessHint();
    apiGet.mockResolvedValue(picker(true));
    const { result } = renderHook(() => useOrgSelection(), { wrapper });
    expect(result.current.contentBlocked).toBe(false); // optimistic, before the answer
    await waitFor(() => expect(result.current.contentBlocked).toBe(true));
    expect(result.current.pickerRequired).toBe(true);
    await waitFor(() => expect(hasOrgAccessHint()).toBe(false));
  });

  it('staff / multi-org first entry with no hint never renders before the picker', async () => {
    apiGet.mockResolvedValue(picker(false));
    const { result } = renderHook(() => useOrgSelection(), { wrapper });
    expect(result.current.contentBlocked).toBe(true);
    await waitFor(() => expect(result.current.access).toBeDefined());
    expect(result.current.contentBlocked).toBe(true);
  });

  it('a single-org answer writes the hint for the current user and marks the visit', async () => {
    setOrgHintUser('u1');
    apiGet.mockResolvedValue(solo);
    const { result } = renderHook(() => useOrgSelection(), { wrapper });
    await waitFor(() => expect(result.current.entryPhase).toBe('visit'));
    expect(hasOrgAccessHint()).toBe(true);
    expect(result.current.contentBlocked).toBe(false);
  });

  it('no user id known: nothing is written', async () => {
    apiGet.mockResolvedValue(solo);
    const { result } = renderHook(() => useOrgSelection(), { wrapper });
    await waitFor(() => expect(result.current.entryPhase).toBe('visit'));
    setOrgHintUser('u1');
    expect(hasOrgAccessHint()).toBe(false);
  });

  it('logout clears the hint', async () => {
    setOrgHintUser('u1'); writeOrgAccessHint();
    await endOrgSelectionBestEffort();
    expect(hasOrgAccessHint()).toBe(false);
    clearOrgAccessHint();
  });
});
