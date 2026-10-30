/**
 * In-page org swap (owner order 2026-10-29) -- the hard reload is gone, its isolation is not.
 *
 * These tests PROVE, against the real shell provider (`OrgScopedQueryClientProvider`):
 *   - no React-Query entry cached under org A exists in the cache the app reads under org B;
 *   - a slow org-A READ and a slow org-A MUTATION (`onSuccess` -> `setQueryData`) that answer
 *     AFTER the swap never reach that cache, and org A is never rendered under org B;
 *   - a stale 409 for a request sent under org A does not undo the new pin;
 *   - realtime is torn down, the stream reconnects without org A's cursor and with the new pin;
 *   - a foreign swap (another tab) purges in-page and re-prompts, like the reload did.
 */
import { act, cleanup, render, renderHook, screen, waitFor } from '@testing-library/react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { QueryClient } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const apiGet = vi.fn();
const apiPut = vi.fn();
const apiDelete = vi.fn();
const removeAllChannels = vi.fn(async () => []);
vi.mock('@noctusai/seed/infra', () => ({
  supabase: { removeAllChannels: () => removeAllChannels() },
  api: {
    get: (...a: unknown[]) => apiGet(...a),
    put: (...a: unknown[]) => apiPut(...a),
    delete: (...a: unknown[]) => apiDelete(...a),
  },
}));

import { ME_ACCESS_QUERY_KEY, resetOrgSelectionPage, useOrgSelection } from './org-selection';
import type { UseOrgSelectionResult } from './org-selection';
import {
  ORG_PIN_HEADER, getOrgPin, getOrgScopeEpoch, notifyOrgSelectionChanged, onOrgScopeReset,
  resetOrgScopeForTests, setOrgPin, useOrgScopeEpoch, useOrgSwapInFlight,
} from './org-pin';
import {
  OrgScopeBoundary, OrgScopedQueryClientProvider, getOrgScopedQueryClient, initOrgScopedQueryClient,
} from './query-client';
import { getOrgVisitOrg, markOrgVisit } from './org-visit';
import { useRealtimeStream } from './realtime';

const HOME = { id: 'h', nome: 'NoctusAI' };
const A = { id: 'a', nome: 'Org A' };
const B = { id: 'b', nome: 'Org B' };
const accessIn = (org: { id: string; nome: string }) => ({
  has_access: true, product_slug: 'p', org,
  org_selection: {
    available: true, required: false, mfa_required: false, acting: true,
    org, home_org: HOME, selection_id: `sel-${org.id}`,
  },
});
const ROWS_KEY = ['product', 'rows'] as const;

function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => { resolve = r; });
  return { promise, resolve };
}

/** Product content: reads rows of the pinned org; exposes a slow write. */
let fireSlowWrite: (() => void) | null = null;
function Content() {
  const rows = useQuery({ queryKey: ROWS_KEY, queryFn: () => apiGet('/rows') as Promise<string[]> });
  const qc = useQueryClient();
  const write = useMutation({ // noc-allow: invalidate-only — test fixture: the commit below IS the late cache write under test
    mutationFn: () => apiPut('/rows/1') as Promise<string[]>,
    onSuccess: (server) => qc.setQueryData(ROWS_KEY, server),
  });
  fireSlowWrite = () => write.mutate();
  if (rows.isPending && !rows.data) return <p>carregando</p>;
  return <ul>{(rows.data ?? []).map((r) => <li key={r}>{r}</li>)}</ul>;
}

let sel: UseOrgSelectionResult;
function Shell() {
  sel = useOrgSelection();
  const epoch = useOrgScopeEpoch();
  const swapping = useOrgSwapInFlight();
  if (swapping) return <p data-testid="swapping">trocando</p>;
  // fixture: the product here only reads once it knows its org (keeps org assertions exact)
  if (sel.contentBlocked || !sel.pin) return <p data-testid="blocked">bloqueado</p>;
  return <Content key={epoch} />;
}

function renderShell() {
  return render(<OrgScopedQueryClientProvider><OrgScopeBoundary><Shell /></OrgScopeBoundary></OrgScopedQueryClientProvider>);
}

const rowsOf = (qc: QueryClient) => qc.getQueryData<string[]>(ROWS_KEY);

describe('in-page org swap: zero cross-org cache', () => {
  const reload = vi.fn();
  const orig = window.location;
  let serverOrg: { id: string; nome: string };

  beforeEach(() => {
    [apiGet, apiPut, apiDelete, reload, removeAllChannels].forEach((m) => m.mockReset());
    removeAllChannels.mockImplementation(async () => []);
    resetOrgSelectionPage(); resetOrgScopeForTests(); setOrgPin(null);
    window.sessionStorage.clear();
    markOrgVisit('a'); // within a visit: this tab chose org A
    serverOrg = A;
    initOrgScopedQueryClient();
    Object.defineProperty(window, 'location', { configurable: true, value: { ...orig, reload } });
    apiPut.mockImplementation(async (path: string, body?: { org_id: string }) => {
      if (path === '/api/me/org-choice') { serverOrg = body!.org_id === 'b' ? B : A; return accessIn(serverOrg); }
      throw new Error(`unexpected PUT ${path}`);
    });
  });
  afterEach(() => {
    cleanup();
    window.sessionStorage.clear();
    Object.defineProperty(window, 'location', { configurable: true, value: orig });
  });

  /** GET router: access follows the server's selection; rows answer for the PINNED org. */
  function routeGets(rows: (pin: string | null) => Promise<string[]> | string[]) {
    apiGet.mockImplementation(async (path: string) => {
      if (path === '/api/me/access') return accessIn(serverOrg);
      if (path === '/api/me/org-choices') return { orgs: [] };
      if (path === '/rows') return rows(getOrgPin());
      throw new Error(`unexpected GET ${path}`);
    });
  }

  it('choose swaps without a reload; nothing cached under org A survives under org B', async () => {
    routeGets((pin) => [`linha-${pin}`]);
    renderShell();
    expect(await screen.findByText('linha-a')).toBeInTheDocument();
    const clientA = getOrgScopedQueryClient();
    expect(rowsOf(clientA)).toEqual(['linha-a']);

    await act(async () => { await sel.choose('b'); });

    expect(await screen.findByText('linha-b')).toBeInTheDocument();
    expect(screen.queryByText('linha-a')).toBeNull();
    expect(reload).not.toHaveBeenCalled();
    const clientB = getOrgScopedQueryClient();
    expect(clientB).not.toBe(clientA);
    expect(rowsOf(clientB)).toEqual(['linha-b']);
    // the old cache is emptied too (nothing of org A lingers anywhere reachable)
    expect(clientA.getQueryCache().getAll()).toHaveLength(0);
    expect(getOrgPin()).toBe('b');
    expect(getOrgVisitOrg()).toBe('b'); // one visit marker, now the new org
    expect(removeAllChannels).toHaveBeenCalled(); // realtime torn down
    // the new org's access was primed from the PUT and re-checked against the server
    expect((clientB.getQueryData(ME_ACCESS_QUERY_KEY) as { org: { id: string } }).org.id).toBe('b');
  });

  it('a slow org-A read and a slow org-A write landing AFTER the swap never reach org B', async () => {
    const slowRead = deferred<string[]>();
    const slowWrite = deferred<string[]>();
    let firstRead = true;
    routeGets((pin) => {
      if (pin === 'a' && firstRead) { firstRead = false; return ['linha-a']; }
      if (pin === 'a') return slowRead.promise; // a refetch under A, still in flight at swap time
      return [`linha-${pin}`];
    });
    renderShell();
    expect(await screen.findByText('linha-a')).toBeInTheDocument();
    const clientA = getOrgScopedQueryClient();
    // start a refetch + a write under org A, both unanswered
    void clientA.refetchQueries({ queryKey: ROWS_KEY });
    apiPut.mockImplementationOnce(() => slowWrite.promise);
    act(() => { fireSlowWrite!(); });

    await act(async () => { await sel.choose('b'); });
    expect(await screen.findByText('linha-b')).toBeInTheDocument();
    const clientB = getOrgScopedQueryClient();

    // org A answers late -- read and write
    await act(async () => {
      slowRead.resolve(['ATRASADO-a']);
      slowWrite.resolve(['ESCRITA-a']);
      await Promise.resolve(); await Promise.resolve();
    });

    expect(rowsOf(clientB)).toEqual(['linha-b']);
    expect(screen.queryByText('ATRASADO-a')).toBeNull();
    expect(screen.queryByText('ESCRITA-a')).toBeNull();
    expect(screen.getByText('linha-b')).toBeInTheDocument();
  });

  it('org A is never rendered while the swap is in flight (transition state instead)', async () => {
    routeGets((pin) => [`linha-${pin}`]);
    const hold = deferred<void>();
    removeAllChannels.mockImplementation(async () => { await hold.promise; return []; });
    renderShell();
    expect(await screen.findByText('linha-a')).toBeInTheDocument();
    let choosing!: Promise<void>;
    act(() => { choosing = sel.choose('b'); });
    expect(await screen.findByTestId('swapping')).toBeInTheDocument();
    expect(screen.queryByText('linha-a')).toBeNull();
    await act(async () => { hold.resolve(); await choosing; });
    expect(await screen.findByText('linha-b')).toBeInTheDocument();
  });

  it('a stale 409 for a request sent under org A does not undo the new pin', async () => {
    routeGets((pin) => [`linha-${pin}`]);
    renderShell();
    await screen.findByText('linha-a');
    await act(async () => { await sel.choose('b'); });
    await screen.findByText('linha-b');
    notifyOrgSelectionChanged('a'); // answered after the swap, sent with the old pin
    expect(getOrgPin()).toBe('b');
    expect(sel.pickerForced).toBe(false);
    notifyOrgSelectionChanged('b'); // a real refusal of the CURRENT pin still clears it
    expect(getOrgPin()).toBeNull();
  });

  it('module-level org state registered for reset is forgotten on the swap', async () => {
    routeGets((pin) => [`linha-${pin}`]);
    const reset = vi.fn();
    const off = onOrgScopeReset(reset);
    renderShell();
    await screen.findByText('linha-a');
    await act(async () => { await sel.choose('b'); });
    expect(reset).toHaveBeenCalledTimes(1);
    off();
  });

  it('foreign swap (another tab changed the selection): in-page purge, then the required picker', async () => {
    routeGets((pin) => [`linha-${pin}`]);
    renderShell();
    await screen.findByText('linha-a');
    const clientA = getOrgScopedQueryClient();
    serverOrg = B; // another tab chose B
    await act(async () => { await clientA.invalidateQueries({ queryKey: ME_ACCESS_QUERY_KEY }); });
    expect(await screen.findByTestId('blocked')).toBeInTheDocument();
    await waitFor(() => expect(sel.pickerRequired).toBe(true));
    expect(reload).not.toHaveBeenCalled();
    expect(getOrgScopedQueryClient()).not.toBe(clientA);
    expect(rowsOf(getOrgScopedQueryClient())).toBeUndefined();
    expect(getOrgPin()).toBeNull();
    expect(getOrgVisitOrg()).toBeNull(); // re-prompt, never adopt the other tab's org
    expect(screen.queryByText('linha-a')).toBeNull();
  });
});

describe('realtime follows the org scope', () => {
  const realFetch = globalThis.fetch;
  afterEach(() => { globalThis.fetch = realFetch; resetOrgScopeForTests(); setOrgPin(null); cleanup(); });

  it('reconnects on a swap with the new pin and without the previous org cursor', async () => {
    const calls: Array<{ url: string; headers: Record<string, string> }> = [];
    globalThis.fetch = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ url: String(url), headers: init?.headers as Record<string, string> });
      const body = calls.length === 1 ? 'id: 9-0\nevent: message.new\ndata: {}\n\n' : '';
      return new Response(new ReadableStream({
        start(c) { if (body) c.enqueue(new TextEncoder().encode(body)); }, // stays open
      }), { status: 200 });
    }) as typeof fetch;
    setOrgPin('a');
    const epochBefore = getOrgScopeEpoch();
    const onEvent = vi.fn();
    renderHook(() => useRealtimeStream('https://x/stream', { getAuthToken: async () => 't', onEvent }));
    await waitFor(() => expect(onEvent).toHaveBeenCalledTimes(1)); // cursor 9-0 recorded under org A
    expect(calls).toHaveLength(1);
    expect(calls[0].headers[ORG_PIN_HEADER]).toBe('a');
    const { beginOrgScopeSwap, endOrgScopeSwap } = await import('./org-pin');
    act(() => { setOrgPin('b'); beginOrgScopeSwap(); endOrgScopeSwap(); });
    await waitFor(() => expect(calls.length).toBeGreaterThanOrEqual(2));
    const reconnect = calls[1];
    expect(reconnect.headers[ORG_PIN_HEADER]).toBe('b');
    expect(reconnect.url).not.toContain('since=');
    expect(getOrgScopeEpoch()).toBe(epochBefore + 1);
  });
});
