/**
 * Org-picker pin store — zero-dependency so `api.ts` / `supabase.ts` can read it
 * without import cycles.
 *
 * The pin is the org id the SPA believes it is acting in. It is sent as
 * `X-Noctus-Acting-Org` on every API request (FastAPI + PostgREST); the server
 * only ever NARROWS on it (409 / falls back to home), it never grants anything.
 * Memory-only on purpose: a reload re-reads `/api/me/access` and re-pins.
 */
import { useSyncExternalStore } from 'react';

export const ORG_PIN_HEADER = 'X-Noctus-Acting-Org';

let pin: string | null = null;
const listeners = new Set<() => void>();
let changedHandler: (() => void) | null = null;
let changedInFlight = false;

export function getOrgPin(): string | null {
  return pin;
}

export function setOrgPin(orgId: string | null): void {
  if (pin === orgId) return;
  pin = orgId;
  listeners.forEach((l) => l());
}

export function subscribeOrgPin(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

/** Registered by `useOrgSelection` (refetch access + reopen picker). */
export function setOrgSelectionChangedHandler(handler: (() => void) | null): void {
  changedHandler = handler;
}

/**
 * Called by the api client on `409 org_selection_changed`. Clears the stale pin
 * first (no request re-sends it, so no loop) and fires the handler once per burst.
 *
 * `sentPin` = the pin the refused request carried (`null` = none). A refusal of a
 * request issued under ANOTHER pin is stale -- it was sent before an in-page org swap
 * and answered after it (the server already moved to the new org) -- so it must not
 * clear the new pin nor reopen the picker. Omitted (legacy callers) = act as before.
 */
export function notifyOrgSelectionChanged(sentPin?: string | null): void {
  if (sentPin !== undefined && sentPin !== pin) return;
  setOrgPin(null);
  if (changedInFlight) return;
  changedInFlight = true;
  try {
    changedHandler?.();
  } finally {
    // Re-arm after the current tick so a burst of parallel 409s collapses to one.
    setTimeout(() => { changedInFlight = false; }, 0);
  }
}

/** `fetch` wrapper for the Supabase browser client (`global.fetch`). */
export function orgPinFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const current = getOrgPin();
  if (!current) return fetch(input, init);
  const headers = new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined));
  headers.set(ORG_PIN_HEADER, current);
  return fetch(input, { ...init, headers });
}

// ---------------------------------------------------------------------------
// Picker-open flag — mirrored by `OrgPickerModal` so a Radix modal (the card
// hub) can yield. A Radix modal makes everything outside its content inert and
// aria-hidden, which buried the picker a 409 just reopened under the card
// (2026-10-10). Zero-dependency (no QueryClient needed to read it).
// ---------------------------------------------------------------------------
let pickerOpen = false;
const pickerOpenListeners = new Set<() => void>();

export function setOrgPickerOpen(open: boolean): void {
  if (pickerOpen === open) return;
  pickerOpen = open;
  pickerOpenListeners.forEach((l) => l());
}

export function getOrgPickerOpen(): boolean {
  return pickerOpen;
}

export function subscribeOrgPickerOpen(listener: () => void): () => void {
  pickerOpenListeners.add(listener);
  return () => { pickerOpenListeners.delete(listener); };
}

/** True while the org picker modal is on screen. */
export function useOrgPickerOpen(): boolean {
  return useSyncExternalStore(subscribeOrgPickerOpen, getOrgPickerOpen, getOrgPickerOpen);
}

// ---------------------------------------------------------------------------
// Org SCOPE -- the in-page org swap (owner order 2026-10-29: swapping orgs must
// not hard-reload). Zero-dependency so `api.ts`, `realtime.ts`, the query-client
// store and the framework shell can all read it without import cycles.
//
// `epoch` increments once per swap. Everything org-scoped keys off it: the shell
// remounts the product subtree (fresh component state, effects -- realtime
// subscriptions included -- re-run), `useRealtimeStream` reconnects without the
// previous org's resume cursor. `inFlight` is true from the start of a swap until
// the new org's `/api/me/access` answered: the product content is NOT rendered
// meanwhile (no flash of the previous org, nothing fetches against a half-swapped
// state). Resets registered with `onOrgScopeReset` run once per swap: the seam for
// module-level org state (job hand-offs, product stores) to forget the old org.
// ---------------------------------------------------------------------------
let orgScopeEpoch = 0;
let orgSwapInFlight = false;
const scopeListeners = new Set<() => void>();
const scopeResets = new Set<() => void>();

function notifyScope(): void {
  scopeListeners.forEach((l) => l());
}

export function getOrgScopeEpoch(): number {
  return orgScopeEpoch;
}

export function getOrgSwapInFlight(): boolean {
  return orgSwapInFlight;
}

export function subscribeOrgScope(listener: () => void): () => void {
  scopeListeners.add(listener);
  return () => { scopeListeners.delete(listener); };
}

/** Start a swap: new epoch, content hidden, every registered reset run. */
export function beginOrgScopeSwap(): number {
  orgScopeEpoch += 1;
  orgSwapInFlight = true;
  scopeResets.forEach((reset) => {
    try {
      reset();
    } catch (err) {
      // One broken reset must not strand the swap half-done; it is reported, never swallowed.
      console.error('[org-scope] a reset handler failed during the org swap', err);
    }
  });
  notifyScope();
  return orgScopeEpoch;
}

/** The new org's access answered: content may render again. Idempotent. */
export function endOrgScopeSwap(): void {
  if (!orgSwapInFlight) return;
  orgSwapInFlight = false;
  notifyScope();
}

/**
 * Register module-level org state to forget on every org swap. Returns the
 * unregister function. Resets must be synchronous and idempotent.
 */
export function onOrgScopeReset(reset: () => void): () => void {
  scopeResets.add(reset);
  return () => { scopeResets.delete(reset); };
}

/** Re-renders on every swap; key org-scoped subtrees with it. */
export function useOrgScopeEpoch(): number {
  return useSyncExternalStore(subscribeOrgScope, getOrgScopeEpoch, getOrgScopeEpoch);
}

/** True while an in-page org swap is in flight. */
export function useOrgSwapInFlight(): boolean {
  return useSyncExternalStore(subscribeOrgScope, getOrgSwapInFlight, getOrgSwapInFlight);
}

/** Tests: back to a fresh page (epoch 0, no swap). Registered resets are kept. */
export function resetOrgScopeForTests(): void {
  orgScopeEpoch = 0;
  orgSwapInFlight = false;
  notifyScope();
}
