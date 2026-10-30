/**
 * Org picker client -- ONE mechanism for platform staff AND multi-org members.
 *
 * Who picks: platform staff (any org licensed for the product), and -- owner decision D1,
 * 2026-10-14 -- a non-staff MEMBER who holds >=2 eligible orgs for THIS product (active,
 * non-customer, licensed, not blocked). The server decides it per user x product and says so
 * in `/api/me/access` (`org_selection.available`); exactly one eligible org => `available` is
 * false => no picker, the server serves that org silently.
 *
 * `useOrgSelection()` exposes the access snapshot, the choices and the
 * choose/end actions. Server is the gate; this is UX only.
 *
 * Swapping orgs is IN-PAGE (owner order 2026-10-29; it used to hard-reload so no
 * cross-org React-Query cache could survive). `swapOrgScope` keeps that guarantee
 * without the reload: the product content unmounts (`org-pin` swap in flight), realtime
 * is torn down, module-level org state is reset, in-flight reads are cancelled and the
 * shell gets a BRAND-NEW QueryClient (`query-client.ts`) while the old one is emptied --
 * so a late org-A answer (query or mutation callback) lands in a client nobody observes.
 * The new client re-runs `/api/me/access`; the content remounts (keyed by the scope
 * epoch) once it answered for the new org. A client that is not the shell's org-scoped
 * one (a product wiring its own provider) cannot be rotated: the swap then falls back to
 * the hard reload, never to a half-isolated cache.
 *
 * Entry handshake (owner decision 2026-10-12, see `org-visit.ts`; extended to members by D1):
 * a page load with no visit marker is an ENTRY. Whenever the picker applies on a picker-ready
 * product, it ends any selection left from a previous visit (`DELETE /api/me/org-choice`),
 * refetches access and keeps the picker REQUIRED (and the product content unrendered) until a
 * choice -- which sets the marker and swaps in-page. Reloads of the same tab keep the choice. So a
 * member's pick lasts one visit, exactly like staff's, never the whole login. When no picker
 * applies, the marker is set and nothing else happens.
 */
import { useCallback, useEffect, useSyncExternalStore } from 'react';
import { QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, supabase } from '@noctusai/seed/infra';

import { ME_ACCESS_QUERY_KEY, isMemberOrgPicker, meAccessQueryOptions, orgSelectionOf } from './access';
import type { MeAccess, OrgChoice, OrgSelectionState } from './access';
import {
  beginOrgScopeSwap, endOrgScopeSwap, getOrgPin, getOrgSwapInFlight, setOrgPin,
  setOrgSelectionChangedHandler, subscribeOrgPin, subscribeOrgScope,
} from './org-pin';
import { isOrgScopedQueryClient, rotateOrgScopedQueryClient } from './query-client';
import { resetJobHandOffs } from './job-polling';
import {
  clearOrgVisitMarker, getOrgEntryPhase, getOrgVisitOrg, markOrgVisit, resetOrgEntryPhase,
  setOrgEntryPhase, subscribeOrgEntryPhase,
} from './org-visit';
import type { OrgEntryPhase } from './org-visit';
import { clearOrgAccessHint, useOrgAccessHint, writeOrgAccessHint } from './org-access-hint';

export { ORG_PIN_HEADER, getOrgPin, setOrgPin } from './org-pin';

export { ME_ACCESS_QUERY_KEY } from './access';

const fetchMeAccess = (): Promise<MeAccess> => api.get<MeAccess>('/api/me/access');
export const ORG_CHOICES_QUERY_KEY = ['me', 'org-choices'] as const;
const CHOICES_STALE_MS = 5 * 60_000;

// Resolves when the entry handshake (DELETE + access refetch) settled, or at once when
// there is none in flight. `choose` awaits it (belt and braces over the disabled buttons).
let entrySettled: Promise<void> = Promise.resolve();

/**
 * Drop every Supabase realtime channel so a stale subscription can't keep
 * streaming the previous org after a swap / stale-pin 409. Cookie-session
 * products have no browser client (`supabase` undefined) → nothing to do.
 */
async function teardownRealtime(): Promise<void> {
  try {
    await (supabase as { removeAllChannels?: () => Promise<unknown> } | undefined)?.removeAllChannels?.();
  } catch (err) {
    // Best-effort, but never silent: with no reload behind it a channel that survives
    // the swap would keep streaming the previous org until the subtree remount drops it.
    console.warn('[org-picker] could not tear down the realtime channels', err);
  }
}

/** Reload hook point (jsdom-friendly, overridable in tests via window.location). */
function reloadPage(): void {
  window.location.reload();
}

/** The PUT's access body, when it really describes the chosen org (else `undefined`). */
function accessFor(orgId: string, body: unknown): MeAccess | undefined {
  const access = body as MeAccess | null | undefined;
  const sel = access && typeof access === 'object' ? orgSelectionOf(access) : null;
  return sel && sel.selection_id && sel.org?.id === orgId ? access as MeAccess : undefined;
}

/**
 * The in-page org swap -- everything the hard reload used to guarantee, minus the reload.
 * Returns `false` (nothing done) when `qc` is not the shell's org-scoped client: the
 * caller then reloads. Order matters:
 *   1. swap in flight + new epoch -> the product subtree unmounts at once (no org-A
 *      frame under org B; no observer left on the old client) and registered resets run;
 *   2. realtime torn down; job hand-offs forgotten (they hold org-A snapshots);
 *   3. in-flight reads cancelled (late answers discarded by the cancelled queries);
 *   4. a brand-new client, primed with the new org's access when the PUT returned it,
 *      replaces the old one; the provider empties the old one (queries + mutations) once
 *      the new one is committed -- every
 *      closure still holding it writes into a cache nobody reads;
 *   5. `/api/me/access` re-runs on the new client (stale-marked, so it refetches on mount).
 * The swap ends (content remounts) when the pin effect sees access for the new org.
 */
async function swapOrgScope(qc: QueryClient, seedAccess?: MeAccess): Promise<boolean> {
  if (!isOrgScopedQueryClient(qc)) return false;
  beginOrgScopeSwap();
  resetJobHandOffs();
  await teardownRealtime();
  await qc.cancelQueries();
  const { next } = rotateOrgScopedQueryClient((fresh) => {
    if (seedAccess) fresh.setQueryData(ME_ACCESS_QUERY_KEY, seedAccess);
  });
  swapClient = next; // the provider empties the previous client once this one is committed
  void next.invalidateQueries({ queryKey: ME_ACCESS_QUERY_KEY });
  return true;
}

/**
 * THE `GET /api/me/access` query -- one key, one fetcher, one cache entry for every consumer
 * (picker, gate, switcher, the shell's effective org, `useIsOrgAdmin`).
 */
export function useMeAccess() {
  return useQuery<MeAccess>(meAccessQueryOptions(fetchMeAccess));
}

/** Never fetches: stands in for the app's client where no `QueryClientProvider` exists. */
let inertClient: QueryClient | null = null;
const NO_CLIENT_MESSAGE = 'No QueryClient set';

/** The provider's client, or null when there is none. `useQueryClient` is always called (stable
 * hook order); ONLY its documented no-provider error means "none" -- anything else is rethrown. */
function useProvidedQueryClient(): QueryClient | null {
  try {
    return useQueryClient();
  } catch (err) {
    if (err instanceof Error && err.message.includes(NO_CLIENT_MESSAGE)) return null;
    throw err;
  }
}

/**
 * `useMeAccess()` for hooks that must also work OUTSIDE a `QueryClientProvider` -- the shell's
 * effective org (`useEffectiveSSOContext`) and so `useIsOrgAdmin`, which product components call
 * and product tests render in isolation. With the app's provider it IS `useMeAccess` (same key,
 * same cache entry). Without one it never fetches and stays `data: undefined`, which every
 * consumer already reads as "access has not answered" -> the SSO token's org/role, the same
 * rule as the pending state. No conditional hook: the client is chosen, the hook always runs.
 */
export function useMeAccessIfProvided() {
  const client = useProvidedQueryClient();
  if (client == null && inertClient == null) inertClient = new QueryClient();
  return useQuery<MeAccess>(
    { ...meAccessQueryOptions(fetchMeAccess), enabled: client != null },
    client ?? (inertClient as QueryClient),
  );
}

export interface UseOrgSelectionResult {
  access: MeAccess | undefined;
  selection: OrgSelectionState;
  /** First load with nothing cached (never `isLoading`). */
  showSkeleton: boolean;
  /** Background refetch with data already on screen. */
  isRefreshing: boolean;
  accessError: boolean;
  choices: OrgChoice[] | undefined;
  /** Choices request in flight with nothing cached (pure query state; never held by the entry handshake). */
  choicesLoading: boolean;
  /**
   * The entry DELETE has not settled yet: the list may already be on screen but a choice
   * must wait (a PUT racing the DELETE would be ended by it).
   */
  chooseBlocked: boolean;
  choicesError: boolean;
  refetchChoices: () => void;
  /** Whether the picker should be visible without user action (non-dismissible). */
  pickerRequired: boolean;
  /**
   * The product's routes/children must NOT render: an entry whose access is still
   * pending, an entry handshake in flight, or a required picker. No picker
   * (non-staff with <2 eligible orgs) within a visit: always `false`. An entry whose access
   * is still pending is NOT blocked when a fresh per-user "no picker" hint exists
   * (`org-access-hint.ts`): the page's queries then run in parallel with `/api/me/access`.
   */
  contentBlocked: boolean;
  /** This page load's entry phase (see `org-visit.ts`). */
  entryPhase: OrgEntryPhase;
  /**
   * The picker applies to a MEMBER (>=2 eligible orgs, D1), not to platform staff: same flow,
   * member presentation (no "acting" banner; the shell switcher instead).
   */
  memberPicker: boolean;
  /** PUT the choice, pin it, swap in-page (reload only for a non-org-scoped client). Rejects with the ApiError on failure. */
  choose: (orgId: string) => Promise<void>;
  choosing: boolean;
  chooseError: unknown;
  /** DELETE the selection (best-effort callers swallow the error). */
  end: () => Promise<void>;
  /** The id currently pinned. */
  pin: string | null;
  /** Picker open state set by a stale-pin 409 / "Trocar org". */
  pickerForced: boolean;
  openPicker: () => void;
  closePicker: () => void;
}

// "Trocar org" / 409 reopen flag — module-level so every consumer shares it.
let forced = false;
const forcedListeners = new Set<() => void>();
/** Exported for tests / logout reset. */
export function setOrgPickerForced(v: boolean) { setForced(v); }
function setForced(v: boolean) {
  if (forced === v) return;
  forced = v;
  forcedListeners.forEach((l) => l());
}
function subscribeForced(l: () => void) {
  forcedListeners.add(l);
  return () => { forcedListeners.delete(l); };
}

// Org this page load's cache belongs to (first pin). Module-level so a 409
// pin-clear can't make the next access refetch look like a first pin.
let pageOrg: string | null = null;
let swapping = false;
// The client a swap waits on (only ITS settled access may disagree with the choice --
// the old client still answers for the old org until the provider re-renders).
let swapClient: QueryClient | null = null;
// A foreign-swap purge is running (re-entrant effect runs must not start a second one).
let purging = false;
/** Tests / logout reset. */
export function resetOrgSelectionPage() {
  pageOrg = null; swapping = false; swapClient = null; purging = false; entrySettled = Promise.resolve(); resetOrgEntryPhase();
  endOrgScopeSwap();
}

/** Entry phases during which no choice exists yet for this page load. */
function isEntry(phase: OrgEntryPhase): boolean {
  return phase === 'entry' || phase === 'ending' || phase === 'ended';
}

export function useOrgSelection():UseOrgSelectionResult {
  const qc = useQueryClient();
  const pin = useSyncExternalStore(subscribeOrgPin, getOrgPin, getOrgPin);
  const pickerForced = useSyncExternalStore(subscribeForced, () => forced, () => forced);
  const entryPhase = useSyncExternalStore(subscribeOrgEntryPhase, getOrgEntryPhase, getOrgEntryPhase);
  const swapInFlight = useSyncExternalStore(subscribeOrgScope, getOrgSwapInFlight, getOrgSwapInFlight);

  const accessQ = useMeAccess();
  const selection = orgSelectionOf(accessQ.data);
  // Early-render hint (org-access-hint.ts): this user is known to hold NO picker. Only ever
  // consulted while access is still pending on an entry; the answer replaces it.
  const noPickerHint = useOrgAccessHint();

  // Pin the org the server says we are in. The FIRST pin of a page load is
  // adopted silently; after that `pageOrg` (the org this page's React-Query
  // cache belongs to) is authoritative and survives a 409 pin-clear, so a
  // different org / ended selection reported by a later access refetch is an
  // org swap (another tab, 409) -> in-page purge + re-evaluation, never a silent re-pin.
  const accessOrgId = selection.available && selection.selection_id && selection.org
    ? selection.org.id : null;
  const accessLoaded = accessQ.data !== undefined;
  // A settled answer (not the primed PUT body still being re-checked).
  const accessSettled = accessLoaded && !accessQ.isFetching;

  // Keep the hint equal to the latest server answer: "no picker" is remembered, anything
  // else (picker applies, no licence, MFA wall) drops it so the next entry waits for access.
  useEffect(() => {
    if (accessQ.data === undefined) return;
    if (!selection.available && accessQ.data.has_access !== false) writeOrgAccessHint();
    else clearOrgAccessHint();
  }, [accessQ.data, selection.available]);

  // Entry handshake -- runs once per page load (module-level phase; every hook
  // instance sees the same transition). Whenever the picker applies (staff, or a member
  // with >=2 eligible orgs -- D1): end the leftover selection BEFORE the product renders,
  // then refetch so the server agrees (`required`).
  useEffect(() => {
    // Read the LIVE phase: sibling hook instances run this effect in the same
    // commit with the same stale render value -- only the first may start the DELETE.
    if (getOrgEntryPhase() !== 'entry' || !accessLoaded) return;
    if (!selection.available) {
      markOrgVisit(); // (sentinel) no picker (<2 eligible orgs / not picker-ready): behaviour unchanged
      setOrgEntryPhase('visit');
      return;
    }
    setOrgEntryPhase('ending');
    let release: () => void = () => {};
    entrySettled = new Promise<void>((resolve) => { release = resolve; });
    void (async () => {
      try {
        await api.delete('/api/me/org-choice');
      } catch (err) {
        // The picker stays REQUIRED client-side regardless (fail toward prompting);
        // logged so a broken DELETE is visible, never silently trusted.
        console.warn('[org-picker] entry: could not end the previous selection', err);
      }
      await qc.refetchQueries({ queryKey: ME_ACCESS_QUERY_KEY });
      setOrgEntryPhase('ended');
      release();
    })();
  }, [entryPhase, accessLoaded, selection.available, qc]);

  useEffect(() => {
    // An entry page load never adopts a selection: the only way out is a choice
    // (which swaps in-page). Within a visit the pin/swap rules below apply unchanged.
    if (entryPhase !== 'visit') return;
    // Cross-tab rule (owner 1A): the marker holds the org THIS tab chose. A picker
    // user whose server-side selection differs (other tab replaced it, ended, or the
    // marker is legacy/unparseable) must re-choose -- never silently adopt. NO entry
    // DELETE: it would end the other tab's live selection; the next PUT replaces it.
    if (pageOrg === null && accessLoaded && selection.available
      && (accessOrgId === null || accessOrgId !== getOrgVisitOrg())) {
      clearOrgVisitMarker();
      setOrgPin(null);
      setForced(false);
      setOrgEntryPhase('ended');
      endOrgScopeSwap(); // the required picker blocks the content from here
      return;
    }
    if (pageOrg === null) {
      if (accessOrgId) { pageOrg = accessOrgId; setOrgPin(accessOrgId); }
      else if (!selection.available) setOrgPin(null);
      if (accessLoaded) endOrgScopeSwap(); // a purge's re-evaluation settled
      return;
    }
    if (accessOrgId === pageOrg) { // same org (restore after a 409 clear) / our own swap landed
      setOrgPin(pageOrg);
      if (!purging) { swapping = false; swapClient = null; endOrgScopeSwap(); }
      return;
    }
    if (purging) return;
    // Our own swap waits for the NEW client's settled access; only that answer naming
    // another org means the server disagrees with the choice (purge + re-evaluate below).
    if (swapping && (qc !== swapClient || !accessSettled)) return;
    // Another org / ended selection under a live page org (another tab, a 409): the old
    // org's cache must not survive. In-page purge, then re-evaluate from a fresh access
    // exactly like the reload did (marker org != server org => required picker).
    const alreadyFresh = swapping && qc === swapClient; // our swap's client: nothing of org A in it
    swapping = true;
    purging = true;
    setForced(false);
    void (async () => {
      try {
        if (!alreadyFresh && !await swapOrgScope(qc)) { await teardownRealtime(); reloadPage(); return; }
        pageOrg = null;
        swapping = false;
        swapClient = null;
        setOrgPin(null);
      } finally {
        purging = false;
      }
    })();
  }, [accessOrgId, selection.available, pin, entryPhase, accessLoaded, accessSettled, qc]);

  // Stale pin (409 org_selection_changed): refetch access + reopen the picker.
  useEffect(() => {
    setOrgSelectionChangedHandler(() => {
      setForced(true);
      void teardownRealtime();
      void qc.invalidateQueries({ queryKey: ME_ACCESS_QUERY_KEY });
    });
    return () => setOrgSelectionChangedHandler(null);
  }, [qc]);

  const choicesQ = useQuery<{ orgs: OrgChoice[] }>({
    queryKey: ORG_CHOICES_QUERY_KEY,
    queryFn: () => api.get<{ orgs: OrgChoice[] }>('/api/me/org-choices'),
    // Starts as soon as the FIRST access says the picker applies -- in parallel with the
    // entry DELETE (the list does not depend on the selection). Never fires without a picker.
    enabled: selection.available && !selection.mfa_required,
    // Kept for the page so "Trocar org" opens instantly; a choice reloads the page anyway.
    staleTime: CHOICES_STALE_MS,
    retry: false,
    placeholderData: (prev) => prev,
  });

  const chooseM = useMutation({ // noc-allow: invalidate-only — the choice IS the org swap: the whole cache is replaced by a fresh client (swapOrgScope), primed with the PUT's access body
    mutationFn: (orgId: string) => api.put<MeAccess>('/api/me/org-choice', { org_id: orgId }),
  });
  const choose = useCallback(async (orgId: string) => {
    await entrySettled; // keep the guard: never PUT before the entry DELETE settled
    const body = await chooseM.mutateAsync(orgId);
    swapping = true; // this IS the swap; the pin effect must not start a second one
    pageOrg = orgId; // the org the NEXT cache belongs to
    markOrgVisit(orgId); // the choice holds for this tab's visit (reloads included)
    setOrgPin(orgId); // every request from here on carries the new org
    setForced(false);
    const inPage = isOrgScopedQueryClient(qc);
    if (inPage) setOrgEntryPhase('visit'); // an entry ends with its choice (a reload re-decides it)
    if (!inPage || !await swapOrgScope(qc, accessFor(orgId, body))) {
      await teardownRealtime();
      reloadPage(); // not the shell's org-scoped client: only a reload isolates it
    }
  }, [chooseM, qc]);

  const end = useCallback(async () => {
    await api.delete('/api/me/org-choice');
    pageOrg = null; // user-initiated end: not a foreign swap
    setOrgPin(null);
  }, []);

  const entering = isEntry(entryPhase);
  const pickerRequired = selection.available && (selection.required || entering);
  const contentBlocked =
    swapInFlight
    || (entryPhase === 'entry' && accessQ.isPending && !accessQ.data && !noPickerHint)
    || (selection.available && (entryPhase === 'entry' || entryPhase === 'ending'))
    || pickerRequired;

  return {
    access: accessQ.data,
    selection,
    showSkeleton: accessQ.isPending && !accessQ.data,
    isRefreshing: accessQ.isFetching && !!accessQ.data,
    accessError: accessQ.isError && !accessQ.data,
    choices: choicesQ.data?.orgs,
    choicesLoading: choicesQ.isPending && choicesQ.fetchStatus !== 'idle' && !choicesQ.data,
    chooseBlocked: selection.available && (entryPhase === 'entry' || entryPhase === 'ending'),
    choicesError: choicesQ.isError && !choicesQ.data,
    refetchChoices: () => { void choicesQ.refetch(); },
    pickerRequired,
    contentBlocked,
    entryPhase,
    memberPicker: isMemberOrgPicker(selection),
    choose,
    choosing: chooseM.isPending,
    chooseError: chooseM.error,
    end,
    pin,
    pickerForced,
    openPicker: () => setForced(true),
    closePicker: () => setForced(false),
  };
}

/**
 * Logout path: end the caller's selections server-side (staff and members alike). Best-effort —
 * a failure (no selection, network) must never block signOut, and core's logout ends all
 * selections anyway.
 */
export async function endOrgSelectionBestEffort(): Promise<void> {
  try {
    // ?all=true ends the caller's selections for EVERY product.
    await api.delete('/api/me/org-choice?all=true');
  } catch {
    /* best-effort by design: signOut proceeds; core logout ends all selections */
  } finally {
    pageOrg = null;
    setOrgPin(null);
    clearOrgAccessHint(); // the next user must not inherit this one's hint
    clearOrgVisitMarker(); // the next load after a logout is an entry
  }
}
