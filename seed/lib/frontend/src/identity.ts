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

/**
 * Best-effort: drop the product's HttpOnly `nai_session` cookie. Never throws.
 *
 * `keepSessionId`: the GoTrue session_id the SPA is still using. The backend
 * revokes the cookie's refresh token UPSTREAM; if the cookie shares the SPA's
 * GoTrue session that would sign the SPA out too (2026-10-22), so the backend
 * skips the upstream revoke when the ids match.
 */
export async function dropProductCookieSession(keepSessionId?: string | null): Promise<void> {
  try {
    await fetch(`${env.BACKEND_API_URL}/api/auth/logout`, {
      method: 'POST',
      credentials: 'include',
      ...(keepSessionId ? { headers: { 'X-Keep-Session': keepSessionId } } : {}),
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

/**
 * The GoTrue `session_id` claim of an access token, or `null` when it cannot be
 * read. NOT an identity or trust decision (the signature is not checked here --
 * identity stays core's `user_id`); it only answers "are these two token pairs
 * the SAME GoTrue session?", i.e. would adopting one roll the other back.
 */
export function goTrueSessionId(accessToken: string | null | undefined): string | null {
  if (!accessToken) return null;
  const part = accessToken.split('.')[1];
  if (!part) return null;
  try {
    const b64 = part.replace(/-/g, '+').replace(/_/g, '/');
    const json = JSON.parse(atob(b64 + '='.repeat((4 - (b64.length % 4)) % 4)));
    return typeof json?.session_id === 'string' && json.session_id ? json.session_id : null;
  } catch {
    return null; // not a JWT we can read: no claim, callers fall back to their default
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
