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
 */
export function notifyOrgSelectionChanged(): void {
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
