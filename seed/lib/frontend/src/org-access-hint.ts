/**
 * "No picker applies to this user" hint -- lets the org gate render a tab's FIRST entry
 * without waiting for `/api/me/access` (the shell waterfall, orbity 2026-10-22).
 *
 * Why: the entry phase (`org-visit.ts`) blocks the product's routes until access answers,
 * because staff and multi-org members must pick an org BEFORE any product query fires.
 * But for a single-org, non-staff member the answer is always "no picker" -- the server
 * serves their org silently, so a page query needs no pin and cannot be wrong. Only that
 * ONE fact is remembered (never the org, role or any access detail), so the gate can
 * decide from it while `/api/me/access` revalidates in the background.
 *
 * Safety:
 *   - Keyed per USER: the record carries the user id and is honoured only when it equals
 *     the user the shell currently reports (`setOrgHintUser`, fed from the auth store).
 *     No user id known yet => no hint => the gate behaves as before (blocked).
 *   - Per product (key carries the slug), TTL-bounded, `localStorage` (a new tab has no
 *     `sessionStorage`; the entry marker is per tab) -- every access try/catch; unavailable
 *     storage reads as "no hint" (fail toward blocking).
 *   - Cleared on logout and on user change; rewritten from EVERY access answer, so a user
 *     who gained a second org / staff role loses it at the first revalidation.
 *   - A contradicting answer (`available: true`) needs no new recovery: the gate's existing
 *     entry rules re-block the content (entry handshake, required picker); a request fired
 *     meanwhile without a pin is answered `409 org_selection_required`, handled by the api
 *     client exactly as before. The server remains the gate; this is UX only.
 *
 * Zero-dependency (like `org-visit.ts`).
 */
import { useEffect, useSyncExternalStore } from 'react';

import { env } from './env';

const KEY_PREFIX = 'noctus:org-access-hint:';
/** A hint older than this is ignored (the user's org set may have changed). */
export const ORG_ACCESS_HINT_TTL_MS = 24 * 60 * 60_000;

interface HintRecord { v: 1; u: string; ts: number }

function hintKey(): string {
  return `${KEY_PREFIX}${env.PRODUCT_SLUG || 'product'}`;
}

let hintUser: string | null = null;
let version = 0;
const listeners = new Set<() => void>();
function bump() { version += 1; listeners.forEach((l) => l()); }

function readRecord(): HintRecord | null {
  try {
    const raw = window.localStorage.getItem(hintKey());
    if (!raw) return null;
    const rec = JSON.parse(raw) as Partial<HintRecord>;
    if (rec?.v !== 1 || typeof rec.u !== 'string' || typeof rec.ts !== 'number') return null;
    return rec as HintRecord;
  } catch {
    return null; // storage unavailable / corrupt: no hint (fail toward blocking)
  }
}

/** Remove the record (logout, user change, contradiction). */
export function clearOrgAccessHint(): void {
  try {
    window.localStorage.removeItem(hintKey());
  } catch {
    // Unreadable storage already reads as "no hint". Nothing to undo.
  }
  bump();
}

/**
 * Tell the store which user the shell currently runs as. A DIFFERENT user than the one the
 * stored record belongs to drops that record at once (never reused across users).
 */
export function setOrgHintUser(userId: string | null | undefined): void {
  const next = userId || null;
  if (hintUser === next) return;
  hintUser = next;
  const rec = readRecord();
  if (rec && rec.u !== next) clearOrgAccessHint();
  else bump();
}

/** Remember that no picker applies to the current user (needs a known user id). */
export function writeOrgAccessHint(): void {
  if (!hintUser) return;
  try {
    const rec: HintRecord = { v: 1, u: hintUser, ts: Date.now() };
    window.localStorage.setItem(hintKey(), JSON.stringify(rec));
  } catch {
    // Not persisted => next tab's first entry waits for access (fail toward blocking).
  }
  bump();
}

/** True when a fresh record exists for exactly the current user. */
export function hasOrgAccessHint(): boolean {
  if (!hintUser) return false;
  const rec = readRecord();
  return !!rec && rec.u === hintUser && Date.now() - rec.ts < ORG_ACCESS_HINT_TTL_MS;
}

/** Reactive `hasOrgAccessHint()`. */
export function useOrgAccessHint(): boolean {
  useSyncExternalStore(
    (l) => { listeners.add(l); return () => { listeners.delete(l); }; },
    () => version, () => version,
  );
  return hasOrgAccessHint();
}

/** Shell wiring: feed the signed-in user id (undefined/null while unknown or signed out). */
export function useOrgHintIdentity(userId: string | null | undefined): void {
  useEffect(() => { setOrgHintUser(userId); }, [userId]);
}

/** Tests: forget the in-memory identity (storage is the test's to clear). */
export function resetOrgAccessHint(): void {
  hintUser = null;
  bump();
}
