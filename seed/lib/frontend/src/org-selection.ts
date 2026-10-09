/**
 * Org picker client (platform staff enter a customer org once per login).
 *
 * `useOrgSelection()` exposes the access snapshot, the choices and the
 * choose/end actions. Server is the gate; this is UX only. Swapping orgs
 * hard-reloads the page so no cross-org React-Query cache survives.
 */
import { useCallback, useEffect, useSyncExternalStore } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, supabase } from '@noctusai/seed/infra';

import { orgSelectionOf } from './access';
import type { MeAccess, OrgChoice, OrgSelectionState } from './access';
import {
  getOrgPin, setOrgPin, setOrgSelectionChangedHandler, subscribeOrgPin,
} from './org-pin';

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
  /** Whether the picker should be visible without user action. */
  pickerRequired: boolean;
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

export function useOrgSelection(): UseOrgSelectionResult {
  const qc = useQueryClient();
  const pin = useSyncExternalStore(subscribeOrgPin, getOrgPin, getOrgPin);
  const pickerForced = useSyncExternalStore(subscribeForced, () => forced, () => forced);

  const accessQ = useQuery<MeAccess>({
    queryKey: ME_ACCESS_QUERY_KEY,
    queryFn: () => api.get<MeAccess>('/api/me/access'),
    staleTime: 60_000,
    retry: false,
    placeholderData: (prev) => prev,
  });
  const selection = orgSelectionOf(accessQ.data);

  // Pin whatever org the server says we are in (staff with a live selection).
  useEffect(() => {
    if (selection.available && selection.selection_id && selection.org) setOrgPin(selection.org.id);
    else if (!selection.available) setOrgPin(null);
  }, [selection.available, selection.selection_id, selection.org]);

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
    setOrgPin(orgId);
    setForced(false);
    await teardownRealtime();
    reloadPage();
  }, [chooseM]);

  const end = useCallback(async () => {
    await api.delete('/api/me/org-choice');
    setOrgPin(null);
  }, []);

  return {
    access: accessQ.data,
    selection,
    showSkeleton: accessQ.isPending && !accessQ.data,
    isRefreshing: accessQ.isFetching && !!accessQ.data,
    accessError: accessQ.isError && !accessQ.data,
    choices: choicesQ.data?.orgs,
    choicesLoading: choicesQ.isPending && choicesQ.fetchStatus !== 'idle' && !choicesQ.data,
    choicesError: choicesQ.isError && !choicesQ.data,
    refetchChoices: () => { void choicesQ.refetch(); },
    pickerRequired: selection.available && selection.required,
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
    setOrgPin(null);
  }
}
