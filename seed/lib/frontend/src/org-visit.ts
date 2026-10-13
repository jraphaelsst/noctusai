/**
 * Org-picker VISIT marker + entry phase (owner decision 2026-10-12).
 *
 * Platform staff choose the org EVERY time they ENTER a product:
 *   - ENTRY = an SSO launch/redeem landing from core (always), or a page load in a
 *     browser tab with no visit marker for this product (new tab, typed URL,
 *     bookmark, reopen after tab close).
 *   - NOT entry: reload (F5) of the same tab, in-app navigation, "Trocar org",
 *     silent token refresh, 409 handling.
 *
 * The marker is per-tab (`sessionStorage`) and per-product (key carries the slug).
 * It is written ONLY after a successful choice (so a reload mid-pick is still an
 * entry) and, for non-staff, as soon as `/api/me/access` says no picker applies.
 * Storage unavailable / throwing => every load is an entry (fail toward prompting).
 *
 * Zero-dependency on the api client so `SSOCallback` can rotate it without
 * dragging `@noctusai/seed/infra` in.
 *
 * KB § PATTERNS/backend/tenancy-license-gate.md § Platform org picker
 */
import { env } from './env';

/** Phase of THIS page load. `unknown` = not yet decided (decided lazily, once). */
export type OrgEntryPhase =
  | 'unknown'
  /** No marker: an entry. Waiting for `/api/me/access`. */
  | 'entry'
  /** Staff entry: `DELETE /api/me/org-choice` + access refetch in flight. */
  | 'ending'
  /** Staff entry handshake done: picker required until a choice (which reloads). */
  | 'ended'
  /** Marker present (or non-staff): within a visit, nothing to do. */
  | 'visit';

const KEY_PREFIX = 'noctus:org-visit:';

function visitKey(): string {
  return `${KEY_PREFIX}${env.PRODUCT_SLUG || 'product'}`;
}

/** True when this tab already has a visit for this product. Throws => `false` (= entry). */
export function hasOrgVisitMarker(): boolean {
  try {
    return window.sessionStorage.getItem(visitKey()) !== null;
  } catch {
    // Storage unavailable (privacy mode / sandboxed iframe): treat as an entry --
    // the documented fail-toward-prompting fallback, not a swallowed error.
    return false;
  }
}

/** Marker value for tabs where no picker applies (non-staff): no org to compare. */
export const NO_PICKER_ORG = '-';

/**
 * Record the visit: the org THIS tab chose (after a successful choice), or
 * `NO_PICKER_ORG` for non-staff. Cross-tab rule (owner 1A, 2026-10-12): one org per
 * product per login, so a load whose server-side selection differs from this org
 * must re-prompt, never silently adopt the other tab's org.
 */
export function markOrgVisit(orgId: string = NO_PICKER_ORG): void {
  try {
    window.sessionStorage.setItem(visitKey(), orgId);
  } catch {
    // Not persisted => the next load is an entry again (fail toward prompting).
  }
}

/**
 * The org this tab chose, or `null` when there is no marker, storage is unavailable,
 * or the value is a legacy timestamp / unparseable (all read as "unknown org" so the
 * caller re-prompts; fail toward prompting). `NO_PICKER_ORG` is returned as-is.
 */
export function getOrgVisitOrg(): string | null {
  try {
    const v = window.sessionStorage.getItem(visitKey());
    if (v === null || v === '' || /^\d+$/.test(v)) return null; // legacy timestamp
    return v;
  } catch {
    return null;
  }
}

/** Forget the visit (SSO landing, logout). */
export function clearOrgVisitMarker(): void {
  try {
    window.sessionStorage.removeItem(visitKey());
  } catch {
    // Unreadable storage already reads as "no marker" => entry. Nothing to undo.
  }
}

let phase: OrgEntryPhase = 'unknown';
const listeners = new Set<() => void>();

/** The phase of this page load (decided on first read from the marker). */
export function getOrgEntryPhase(): OrgEntryPhase {
  if (phase === 'unknown') phase = hasOrgVisitMarker() ? 'visit' : 'entry';
  return phase;
}

export function setOrgEntryPhase(next: OrgEntryPhase): void {
  if (phase === next) return;
  phase = next;
  listeners.forEach((l) => l());
}

export function subscribeOrgEntryPhase(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

/**
 * The SSO redeem landing is ALWAYS an entry, even in the same tab: drop the
 * marker and re-decide the phase (the SPA navigates in-place afterwards).
 */
export function beginOrgVisitEntry(): void {
  clearOrgVisitMarker();
  setOrgEntryPhase('entry');
}

/** Tests: forget the decided phase (the marker itself lives in sessionStorage). */
export function resetOrgEntryPhase(): void {
  phase = 'unknown';
  listeners.forEach((l) => l());
}
