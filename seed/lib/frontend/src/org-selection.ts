/**
 * Org picker client (platform staff choose the org EVERY time they enter a product).
 *
 * `useOrgSelection()` exposes the access snapshot, the choices and the
 * choose/end actions. Server is the gate; this is UX only. Swapping orgs
 * hard-reloads the page so no cross-org React-Query cache survives.
 *
 * Entry handshake (owner decision 2026-10-12, see `org-visit.ts`): a page load
 * with no visit marker is an ENTRY. For staff on a picker-ready product it ends
 * any selection left from a previous visit (`DELETE /api/me/org-choice`), refetches
 * access and keeps the picker REQUIRED (and the product content unrendered) until a
 * choice -- which sets the marker and reloads. Reloads of the same tab keep the
 * choice. Non-staff: the marker is set, nothing else happens.
 */
import { useCallback, useEffect, useSyncExternalStore } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, supabase } from '@noctusai/seed/infra';

import { orgSelectionOf } from './access';
import type { MeAccess, OrgChoice, OrgSelectionState } from './access';
import {
  getOrgPin, setOrgPin, setOrgSelectionChangedHandler, subscribeOrgPin,
} from './org-pin';
import {
  clearOrgVisitMarker, getOrgEntryPhase, markOrgVisit, resetOrgEntryPhase,
  setOrgEntryPhase, subscribeOrgEntryPhase,
} from './org-visit';
import type { OrgEntryPhase } from './org-visit';

export { ORG_PIN_HEADER, getOrgPin, setOrgPin } from './org-pin';

export const ME_ACCESS_QUERY_KEY = ['me', 'access'] as const;
export const ORG_CHOICES_QUERY_KEY = ['me', 'org-choices'] as const;

/**
 * Drop every Supabase realtime channel so a stale subscription can't keep
 * streaming the previous org after a swap / stale-pin 409. Cookie-session
 * products have no browser client (`supabase` undefined) → nothing to do.
 */
async function teardownRealtime(): Promise<void> {
  try {
    await (supabase as { removeAllChannels?: () => Promise<unknown> } | undefined)?.removeAllChannels?.();
  } catch {
    /* best-effort: the reload that follows drops the sockets anyway */
  }
}

/** Reload hook point (jsdom-friendly, overridable in tests via window.location). */
function reloadPage(): void {
  window.location.reload();
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
  choicesLoading: boolean;
  choicesError: boolean;
  refetchChoices: () => void;
  /** Whether the picker should be visible without user action (non-dismissible). */
  pickerRequired: boolean;
  /**
   * The product's routes/children must NOT render: an entry whose access is still
   * pending, a staff entry handshake in flight, or a required picker. Non-staff
   * within a visit: always `false`.
   */
  contentBlocked: boolean;
  /** This page load's entry phase (see `org-visit.ts`). */
  entryPhase: OrgEntryPhase;
  /** PUT the choice, pin it, reload. Rejects with the ApiError on failure. */
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
/** Tests / logout reset. */
export function resetOrgSelectionPage() { pageOrg = null; swapping = false; resetOrgEntryPhase(); }

/** Entry phases during which no choice exists yet for this page load. */
function isEntry(phase: OrgEntryPhase): boolean {
  return phase === 'entry' || phase === 'ending' || phase === 'ended';
}

export function useOrgSelection():UseOrgSelectionResult {
  const qc = useQueryClient();
  const pin = useSyncExternalStore(subscribeOrgPin, getOrgPin, getOrgPin);
  const pickerForced = useSyncExternalStore(subscribeForced, () => forced, () => forced);
  const entryPhase = useSyncExternalStore(subscribeOrgEntryPhase, getOrgEntryPhase, getOrgEntryPhase);

  const accessQ = useQuery<MeAccess>({
    queryKey: ME_ACCESS_QUERY_KEY,
    queryFn: () => api.get<MeAccess>('/api/me/access'),
    staleTime: 60_000,
    retry: false,
    placeholderData: (prev) => prev,
  });
  const selection = orgSelectionOf(accessQ.data);

  // Pin the org the server says we are in. The FIRST pin of a page load is
  // adopted silently; after that `pageOrg` (the org this page's React-Query
  // cache belongs to) is authoritative and survives a 409 pin-clear, so a
  // different org / ended selection reported by a later access refetch is an
  // org swap (another tab, 409) -> hard reload, never a silent re-pin.
  const accessOrgId = selection.available && selection.selection_id && selection.org
    ? selection.org.id : null;
  const accessLoaded = accessQ.data !== undefined;

  // Entry handshake -- runs once per page load (module-level phase; every hook
  // instance sees the same transition). Staff: end the leftover selection BEFORE
  // the product renders, then refetch so the server agrees (`required`).
  useEffect(() => {
    // Read the LIVE phase: sibling hook instances run this effect in the same
    // commit with the same stale render value -- only the first may start the DELETE.
    if (getOrgEntryPhase() !== 'entry' || !accessLoaded) return;
    if (!selection.available) {
      markOrgVisit(); // non-staff / not picker-ready: no picker, behaviour unchanged
      setOrgEntryPhase('visit');
      return;
    }
    setOrgEntryPhase('ending');
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
    })();
  }, [entryPhase, accessLoaded, selection.available, qc]);

  useEffect(() => {
    // An entry page load never adopts a selection: the only way out is a choice
    // (which reloads). Within a visit the pin/swap rules below apply unchanged.
    if (entryPhase !== 'visit') return;
    if (pageOrg === null) {
      if (accessOrgId) { pageOrg = accessOrgId; setOrgPin(accessOrgId); }
      else if (!selection.available) setOrgPin(null);
      return;
    }
    if (accessOrgId === pageOrg) { setOrgPin(pageOrg); return; } // same org: restore after a 409 clear
    if (swapping) return;
    swapping = true;
    setForced(false);
    void teardownRealtime().finally(reloadPage);
  }, [accessOrgId, selection.available, pin, entryPhase]);

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
    enabled: selection.available && !selection.mfa_required,
    staleTime: 0,
    retry: false,
    placeholderData: (prev) => prev,
  });

  const chooseM = useMutation({
    mutationFn: (orgId: string) => api.put<MeAccess>('/api/me/org-choice', { org_id: orgId }),
  });
  const choose = useCallback(async (orgId: string) => {
    await chooseM.mutateAsync(orgId);
    swapping = true; // the reload below IS the swap; the pin effect must not double-fire
    markOrgVisit(); // the choice holds for this tab's visit (reloads included)
    setOrgPin(orgId);
    setForced(false);
    await teardownRealtime();
    reloadPage();
  }, [chooseM]);

  const end = useCallback(async () => {
    await api.delete('/api/me/org-choice');
    pageOrg = null; // user-initiated end: not a foreign swap
    setOrgPin(null);
  }, []);

  const entering = isEntry(entryPhase);
  const pickerRequired = selection.available && (selection.required || entering);
  const contentBlocked =
    (entryPhase === 'entry' && accessQ.isPending && !accessQ.data)
    || (selection.available && (entryPhase === 'entry' || entryPhase === 'ending'))
    || pickerRequired;

  return {
    access: accessQ.data,
    selection,
    showSkeleton: accessQ.isPending && !accessQ.data,
    isRefreshing: accessQ.isFetching && !!accessQ.data,
    accessError: accessQ.isError && !accessQ.data,
    choices: choicesQ.data?.orgs,
    // Choosing is held until the entry DELETE settled (a PUT racing it would be ended).
    choicesLoading: (choicesQ.isPending && choicesQ.fetchStatus !== 'idle' && !choicesQ.data)
      || (selection.available && (entryPhase === 'entry' || entryPhase === 'ending')),
    choicesError: choicesQ.isError && !choicesQ.data,
    refetchChoices: () => { void choicesQ.refetch(); },
    pickerRequired,
    contentBlocked,
    entryPhase,
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
 * Logout path: end this product's selection server-side. Best-effort — a
 * failure (no selection, non-staff 403, network) must never block signOut, and
 * core's logout ends all selections anyway.
 */
export async function endOrgSelectionBestEffort(): Promise<void> {
  try {
    // ?all=true ends the selections for EVERY product (staff-only server-side).
    await api.delete('/api/me/org-choice?all=true');
  } catch {
    /* best-effort by design: signOut proceeds; core logout ends all selections */
  } finally {
    pageOrg = null;
    setOrgPin(null);
    clearOrgVisitMarker(); // the next load after a logout is an entry
  }
}
