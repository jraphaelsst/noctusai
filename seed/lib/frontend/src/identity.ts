/**
 * Browser identity hygiene for the Supabase-session products.
 *
 * Two things the SPA must do when the account in this origin is not (or no
 * longer) the account that should be acting:
 *
 * 1. `isAuthRejection` / `verifySessionWithServer` — the boot/focus check. The
 *    locally stored session is only a CLAIM; `auth.getUser()` asks the auth
 *    server. Only an authoritative rejection ends the session — a network
 *    error or 5xx never does (an auth-server outage must not log out the fleet).
 * 2. `clearLocalIdentity` — everything the SPA owns that is scoped to the
 *    previous user, so an account switch cannot leak the old identity.
 */
import { env } from './env';
import { setOrgPin } from './org-pin';
import { ACTIVITY_REFRESH_STORAGE_KEY } from './design-system/useActivityRefresh';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnySupabaseClient = { auth: any };

const AUTH_REJECTION_CODES = new Set(['session_not_found', 'bad_jwt', 'user_not_found']);

/** True only for an authoritative "this session is not valid" answer. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function isAuthRejection(error: any): boolean {
  if (!error) return false;
  if (error.name === 'AuthSessionMissingError') return true;
  if (error.name === 'AuthRetryableFetchError') return false;
  if (typeof error.code === 'string' && AUTH_REJECTION_CODES.has(error.code)) return true;
  return error.name === 'AuthApiError' && (error.status === 401 || error.status === 403);
}

/** Best-effort: drop the product's HttpOnly `nai_session` cookie. Never throws. */
export async function dropProductCookieSession(): Promise<void> {
  try {
    await fetch(`${env.BACKEND_API_URL}/api/auth/logout`, {
      method: 'POST',
      credentials: 'include',
    });
  } catch {
    /* best-effort: a failed cookie drop must never block the flow */
  }
}

/** Clear SPA state scoped to the previous user (pin + per-user localStorage). */
export function clearLocalIdentity(): void {
  setOrgPin(null);
  try {
    localStorage.removeItem(ACTIVITY_REFRESH_STORAGE_KEY);
  } catch {
    /* storage unavailable (private mode) */
  }
}

export type SessionVerdict = 'valid' | 'rejected' | 'unverified';

/**
 * Ask the auth server whether the stored session is still valid.
 * `rejected` -> caller must end the local session; `unverified` (network/5xx/
 * unexpected) -> keep it and retry at the next trigger.
 */
export async function verifySessionWithServer(supabase: AnySupabaseClient): Promise<SessionVerdict> {
  try {
    const { data, error } = await supabase.auth.getUser();
    if (error) {
      if (isAuthRejection(error)) return 'rejected';
      // eslint-disable-next-line no-console
      console.warn('[auth] identity check inconclusive, keeping session:', error.message ?? error);
      return 'unverified';
    }
    return data?.user ? 'valid' : 'unverified';
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn('[auth] identity check failed, keeping session:', err);
    return 'unverified';
  }
}
