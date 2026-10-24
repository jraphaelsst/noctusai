/**
 * Shared auth initialization hook.
 *
 * Handles the common pattern of:
 * 1. Getting the initial Supabase session
 * 2. Calling setUser + setInitialized
 * 3. Subscribing to auth state changes
 *
 * Products that need extra logic (e.g. ERP's activity tracking) can still
 * use this as a base and add their own effects alongside it.
 *
 * Two seed-level fixes lifted 2026-05-16 from the youtube-crawler
 * workspace (SESSION-NOTES_seed-frontend-standalone-drift +
 * SEED-NEEDS-DEV-AUTH-AND-SQLITE):
 *
 * 1. `useAuthReady()` — a global "auth restore has resolved" signal so
 *    data hooks can defer until the session is attached. Fixes the
 *    pre-auth query race where `/api/notificacoes*` fired before
 *    `getSession()` resolved → spurious 401 → "servidor indisponível"
 *    toast on every page load in standalone deploys.
 * 2. `VITE_DEV_AUTOLOGIN` — dev-only synthetic session that skips the
 *    Landing/Login redirect (pairs with the backend `SEED_DEV_AUTH`
 *    bypass). Loud console banner; default-OFF; build-time inlined.
 */
import { useEffect, useState } from 'react';
import type { User } from '@supabase/supabase-js';

import { env } from './env';
import { dropProductCookieSession, goTrueSessionId, verifySessionWithServer } from './identity';
import { isTransientHttpStatus, refreshWithBackoff, type RefreshAttempt, type RefreshWithBackoffOptions } from './api';
import { autoRetryDelayMs } from './retry';
import { adoptRotatedPair } from './session-ending';

// How a session ends (expiry = local only; explicit Sair = the only server revoke).
export {
  adoptRotatedPair,
  endSessionLocally,
  signOutExplicitly,
  type StoredSessionPair,
  type EndSessionLocallyOptions,
  type SignOutExplicitlyOptions,
} from './session-ending';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnySupabaseClient = { auth: any };

// ---------------------------------------------------------------------------
// Auth-ready signal (root-cause-1 fix)
// ---------------------------------------------------------------------------
//
// Module-scoped so every consumer observes the SAME readiness state
// regardless of which component subscribes. Flips to `true` exactly once
// when the initial session restore resolves (success OR no-session both
// count as "ready" — readiness means "we know the auth state", not
// "logged in"). Auth-dependent data hooks gate on this AND `!!user` so
// the first request never races ahead of the restored token.
let _authReady = false;
const _authReadyListeners = new Set<(ready: boolean) => void>();

function markAuthReady(): void {
  if (_authReady) return;
  _authReady = true;
  _authReadyListeners.forEach((fn) => fn(true));
}

/** Reactive "initial auth restore has resolved" flag. */
export function useAuthReady(): boolean {
  const [ready, setReady] = useState(_authReady);
  useEffect(() => {
    if (_authReady) {
      setReady(true);
      return;
    }
    const listener = (r: boolean) => setReady(r);
    _authReadyListeners.add(listener);
    return () => {
      _authReadyListeners.delete(listener);
    };
  }, []);
  return ready;
}

// ---------------------------------------------------------------------------
// Boot "reconnecting" signal + the ONE boot verdict (F74, prod 2026-10-24)
// ---------------------------------------------------------------------------
//
// A page load that lands in the few seconds of a container swap / tunnel
// restart (502 / 530 / network error) must NEVER be read as "not signed in":
// that sent a logged-in tab to the public Landing although the stored session
// was intact and GoTrue had logged nothing. Boot has exactly three outcomes:
//   `user`      -- a session was restored
//   `none`      -- the auth server ANSWERED that there is no session (-> login)
//   `transient` -- it could not be asked (-> stay on the skeleton, show
//                  "Reconectando...", retry paced by the canonical schedule)
// `transient` never reaches `setUser(null)` / `setInitialized()`.
export type BootVerdict<U> = { kind: 'user'; user: U } | { kind: 'none' } | { kind: 'transient' };

let _authReconnecting = false;
const _reconnectingListeners = new Set<(r: boolean) => void>();

function setAuthReconnecting(value: boolean): void {
  if (_authReconnecting === value) return;
  _authReconnecting = value;
  _reconnectingListeners.forEach((fn) => fn(value));
}

/** True while boot could not reach the auth server and is retrying (show "Reconectando..."). */
export function useAuthReconnecting(): boolean {
  const [reconnecting, setReconnecting] = useState(_authReconnecting);
  useEffect(() => {
    setReconnecting(_authReconnecting);
    _reconnectingListeners.add(setReconnecting);
    return () => {
      _reconnectingListeners.delete(setReconnecting);
    };
  }, []);
  return reconnecting;
}

/**
 * Run a boot restore until it yields a DEFINITIVE verdict. A `transient` result
 * is retried forever on the canonical schedule (1s, 3s, 9s, then every 9s) --
 * boot cannot conclude "signed out" from an unanswered question.
 */
async function resolveBootVerdict<U>(
  attempt: () => Promise<BootVerdict<U>>,
  isDisposed: () => boolean,
): Promise<BootVerdict<U> | null> {
  for (let i = 0; ; i++) {
    let verdict: BootVerdict<U>;
    try {
      verdict = await attempt();
    } catch {
      verdict = { kind: 'transient' };
    }
    if (isDisposed()) return null;
    if (verdict.kind !== 'transient') {
      setAuthReconnecting(false);
      return verdict;
    }
    setAuthReconnecting(true);
    await new Promise((r) => setTimeout(r, autoRetryDelayMs(i)));
    if (isDisposed()) return null;
  }
}

/** Classify ONE supabase `getSession()` result at boot. */
export function classifyBootSession(res: {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data?: { session?: any } | null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  error?: any;
}): BootVerdict<User> {
  const session = res?.data?.session;
  if (session) return { kind: 'user', user: session.user ?? null };
  const error = res?.error;
  if (!error) return { kind: 'none' };
  const status: number | undefined = typeof error.status === 'number' ? error.status : undefined;
  // supabase-js returns `session: null` + AuthRetryableFetchError when the
  // refresh of an expired access token could not reach GoTrue: not a verdict.
  if (error.name === 'AuthRetryableFetchError' || isTransientHttpStatus(status)) return { kind: 'transient' };
  return { kind: 'none' };
}

/** Classify the cookie-session `GET /api/auth/me` boot answer. */
export function classifyBootMeStatus(status: number): 'ok' | 'none' | 'transient' {
  if (status >= 200 && status < 300) return 'ok';
  return isTransientHttpStatus(status) ? 'transient' : 'none';
}

// ---------------------------------------------------------------------------
// Supabase session refresh — transient ≠ dead
// ---------------------------------------------------------------------------

/**
 * Classify ONE `supabase.auth.refreshSession()` result.
 *
 * supabase-js reports a refresh it could not complete as `{ error }` with
 * either `AuthRetryableFetchError` (no response, or a 502/503/504 — status 0
 * or 5xx) or `AuthApiError` (the Auth server answered). Only an answered 4xx
 * (invalid / revoked / already-used refresh token, no session) means the
 * session is dead; a 5xx/429/network error means "ask again later".
 */
export function classifySupabaseRefresh(result: {
  data?: { session?: { access_token?: string } | null } | null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  error?: any;
}): RefreshAttempt {
  const token = result?.data?.session?.access_token;
  if (token) return { kind: 'token', token };
  const error = result?.error;
  if (!error) return { kind: 'dead' }; // answered: there is no session
  const status: number | undefined = typeof error.status === 'number' ? error.status : undefined;
  if (error.name === 'AuthRetryableFetchError' || isTransientHttpStatus(status)) {
    return { kind: 'transient', reason: `${error.name ?? 'AuthError'} ${status ?? ''}`.trim() };
  }
  return { kind: 'dead' };
}

/** The refresh token currently in this origin's shared session slot, or `null`. */
async function storedRefreshToken(supabase: AnySupabaseClient): Promise<{ refreshToken: string | null; accessToken: string | null }> {
  try {
    const session = (await supabase.auth.getSession?.())?.data?.session;
    return { refreshToken: session?.refresh_token ?? null, accessToken: session?.access_token ?? null };
  } catch {
    return { refreshToken: null, accessToken: null };
  }
}

/**
 * ONE browser refresh of the shared session, classified -- with the rotation
 * check: a refusal (`refresh_token_already_used`) or a discarded commit while
 * the slot now holds a DIFFERENT refresh token than the one we started from
 * means another tab of this origin rotated the chain -- the session is alive,
 * adopt the winner's token. The browser is the only owner of this chain; no
 * server ever refreshes it, so a refusal is only "dead" when the slot still
 * holds the token that was refused.
 */
async function refreshSharedSession(supabase: AnySupabaseClient): Promise<RefreshAttempt> {
  const before = await storedRefreshToken(supabase);
  const result = await supabase.auth.refreshSession();
  const discarded = result?.error?.name === 'AuthRefreshDiscardedError';
  const verdict = discarded ? ({ kind: 'dead' } as RefreshAttempt) : classifySupabaseRefresh(result);
  if (verdict.kind !== 'dead') return verdict;
  const after = await storedRefreshToken(supabase);
  // A discarded commit means a concurrent refresh in this tab won the slot.
  const adopted = discarded ? after.accessToken : adoptRotatedPair(before.refreshToken, after);
  return adopted ? { kind: 'token', token: adopted } : { kind: 'dead' };
}

/**
 * `onTokenExpired` for any seed product on a supabase-js session: refreshes,
 * retries transient failures with backoff, resolves `null` only when Supabase
 * authoritatively refused AND no other tab holds a rotated pair, and throws
 * `TransientAuthError` otherwise — so a deploy window never logs the user out
 * (2026-10-03). Wired by `createProductInfra` (`@noctusai/seed/infra`).
 */
export function createSupabaseTokenRefresher(
  supabase: AnySupabaseClient,
  options?: RefreshWithBackoffOptions,
): () => Promise<string | null> {
  return () => refreshWithBackoff(() => refreshSharedSession(supabase), options);
}

/**
 * Confirm a "this session is dead" CLAIM (a 401, a rejected `getUser()`) by
 * the only authoritative test: one browser refresh of the shared chain.
 *
 *  - refresh succeeds, or another tab already rotated the slot → `alive`
 *    (a stale access token was rejected, not the session);
 *  - refresh unanswered (network / 5xx / 429) → `transient`;
 *  - refresh authoritatively refused while the slot still holds the refused
 *    token → `dead`. supabase-js has then already purged its own slot
 *    LOCALLY; nobody calls GoTrue `/logout`.
 *
 * 🔴 Never `signOut()` on a dead verdict (prod 2026-10-13 + 2026-10-23):
 * `signOut({ scope: 'local' })` is a GoTrue `/logout` that deletes the session
 * server-side for every tab; a wrong verdict there is unrecoverable.
 */
export async function confirmSessionAfterRejection(supabase: AnySupabaseClient): Promise<SessionLiveness> {
  try {
    const verdict = await refreshSharedSession(supabase);
    if (verdict.kind === 'token') return 'alive';
    return verdict.kind === 'transient' ? 'transient' : 'dead';
  } catch {
    return 'transient';
  }
}

/** Verdict of asking GoTrue "is this session still alive?". */
export type SessionLiveness = 'alive' | 'dead' | 'transient';

/**
 * Ask GoTrue (`auth.getUser()` — a server round-trip, NOT a local read)
 * whether the current session is alive. `dead` only when GoTrue ANSWERED that
 * there is no usable session (no local session, 401/403/other non-transient
 * 4xx such as `session_not_found` / `bad_jwt`); `transient` when it could not
 * be asked (network, 408/425/429/5xx, a throw) — the unanswered case must
 * never destroy a session.
 */
export async function probeSessionLiveness(supabase: AnySupabaseClient): Promise<SessionLiveness> {
  try {
    const res = await supabase.auth.getUser();
    const error = res?.error;
    if (!error) return res?.data?.user ? 'alive' : 'dead';
    if (error.name === 'AuthSessionMissingError') return 'dead';
    const status: number | null | undefined = error.status;
    if (error.name === 'AuthRetryableFetchError' || isTransientHttpStatus(status)) return 'transient';
    return 'dead';
  } catch {
    return 'transient';
  }
}

/**
 * The `onUnauthenticated` handler for a supabase-js product: a request came
 * back 401 with no recovery (no token, or the refresh was REFUSED / the retry
 * still 401'd). That is a CLAIM that the session is dead, not proof — so the
 * handler CONFIRMS with GoTrue before destroying anything:
 *
 *  - `dead` (GoTrue says no usable session) → confirm with one refresh
 *    (`confirmSessionAfterRejection`); only a confirmed death clears the auth
 *    store, which flips the app's `!user` gate in `createProductApp` and
 *    redirects to Landing/login. Never `signOut()` (a GoTrue `/logout`).
 *  - `alive` → the 401 came from the product backend for another reason; do
 *    NOT sign out, do NOT clear the user. Warn (with the path) and let the
 *    caller's error propagate.
 *  - `transient` (GoTrue unreachable) → keep the session, same as alive.
 *
 * 🔴 Why confirm (2026-10-13, prod): `signOut({ scope: 'local' })` is NOT a
 * purely local purge — supabase-js still calls GoTrue `/logout?scope=local`,
 * which DELETES the current session server-side. Every tab of a product shares
 * that one session (same localStorage), so ONE tab's false dead-session verdict
 * destroyed a healthy session for all of them and every later request 401'd
 * `session_not_found`. The previous comment ("only this tab's session is
 * dead") was wrong. 2026-10-23: the dead path no longer calls `signOut` at
 * all — the refresh that confirms death makes supabase-js purge its slot
 * locally; a verdict never reaches GoTrue `/logout`.
 *
 * Idempotent (a dead session produces a BURST of 401s — collapsed to one
 * verdict; the guard resets after 3s so a later genuine re-login → expiry can
 * redirect again); never acts on a public auth route (/login, /sso); never
 * throws into the fetch path.
 */
export function createDeadSessionHandler(
  supabase: AnySupabaseClient,
  useAuthStore: { getState: () => { setUser?: (u: null) => void } },
): () => void {
  let handling = false;
  return () => {
    if (handling) return;
    const path = typeof window !== 'undefined' ? window.location.pathname : '';
    if (path.startsWith('/login') || path.startsWith('/sso')) return;
    handling = true;
    if (typeof window !== 'undefined') {
      window.setTimeout(() => { handling = false; }, 3000);
    }
    void (async () => {
      const verdict = await probeSessionLiveness(supabase);
      if (verdict !== 'dead') {
        // eslint-disable-next-line no-console
        console.warn(
          `[auth] 401 on ${path || '(unknown path)'} but the session is ${verdict} per GoTrue — keeping it signed in`,
        );
        return;
      }
      // GoTrue says the access token is not usable — confirm with ONE refresh
      // before ending anything (an expired token is not a dead session).
      const confirmed = await confirmSessionAfterRejection(supabase);
      if (confirmed !== 'dead') {
        // eslint-disable-next-line no-console
        console.warn(`[auth] 401 on ${path || '(unknown path)'} but a refresh shows the session is ${confirmed} — keeping it signed in`);
        return;
      }
      // Dead: supabase-js already purged its slot locally. No signOut — that is
      // a GoTrue /logout, never ours to send on a verdict.
      try { useAuthStore.getState().setUser?.(null); } catch { /* best-effort */ }
    })();
  };
}

// ---------------------------------------------------------------------------
// Dev autologin (root-cause: no day-one dev login)
// ---------------------------------------------------------------------------

/** Synthetic dev user — mirrors the backend `_DevUser` shape. */
function devAutologinUser(): User {
  // Cast: we only populate the fields the seed reads (id, email,
  // user_metadata, app_metadata); the supabase User type has many more.
  return {
    id: '00000000-0000-0000-0000-0000000000de',
    email: 'dev@noctusai.local',
    user_metadata: { org_id: '00000000-0000-0000-0000-0000000000a0', role: 'owner' },
    app_metadata: { provider: 'seed-dev-auth' },
    aud: 'authenticated',
    created_at: new Date(0).toISOString(),
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any as User;
}

/** Minimum gap between server identity checks, per tab. */
export const IDENTITY_CHECK_THROTTLE_MS = 60_000;

export function useSupabaseAuthInit(
  supabase: AnySupabaseClient,
  setUser: (user: User | null) => void,
  setInitialized?: () => void,
) {
  useEffect(() => {
    if (env.DEV_AUTOLOGIN) {
      // Loud, unmissable — must never ship to prod unnoticed.
      // eslint-disable-next-line no-console
      console.warn(
        '%c[DEV AUTOLOGIN]%c synthetic session active as dev@noctusai.local — ' +
          'this MUST be off in production (VITE_DEV_AUTOLOGIN).',
        'background:#b91c1c;color:#fff;padding:2px 6px;border-radius:3px',
        'color:#b91c1c',
      );
      setUser(devAutologinUser());
      setInitialized?.();
      markAuthReady();
      return;
    }

    let disposed = false;
    let lastCheck = 0;
    // Server-validated identity check (boot + tab refocus, <= 1/min per tab).
    // The stored session is only a claim; only an auth REJECTION ends it.
    const verify = async () => {
      const now = Date.now();
      if (now - lastCheck < IDENTITY_CHECK_THROTTLE_MS) return;
      lastCheck = now;
      const verdict = await verifySessionWithServer(supabase);
      if (disposed || verdict !== 'rejected') return;
      // A rejection is a claim about the ACCESS token (expired, superseded by a
      // rotation in this or another tab). Confirm with one refresh of the shared
      // chain; only a refusal of the token the slot still holds ends the session.
      let keepId: string | null = null;
      try {
        keepId = goTrueSessionId((await supabase.auth.getSession())?.data?.session?.access_token);
      } catch { /* no claim */ }
      const confirmed = await confirmSessionAfterRejection(supabase);
      if (disposed || confirmed !== 'dead') return;
      // Dead: supabase-js already purged the slot locally — never signOut here
      // (a GoTrue /logout on a verdict, prod 2026-10-23).
      await dropProductCookieSession(keepId);
      if (!disposed) setUser(null);
    };

    void resolveBootVerdict<User>(
      async () => classifyBootSession(await supabase.auth.getSession()),
      () => disposed,
    ).then((verdict) => {
      if (!verdict) return;
      const user = verdict.kind === 'user' ? verdict.user : null;
      setUser(user);
      setInitialized?.();
      markAuthReady();
      if (verdict.kind === 'user') void verify();
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event: any, session: any) => {
      if (event === 'SIGNED_OUT' && !session) {
        // Never a silent redirect to Landing (2026-10-22, prod: an admin active for ~1h
        // was signed out mid-session). supabase-js emits SIGNED_OUT both for a real
        // sign-out and when a background refresh is refused (reuse race between
        // tabs/clients). Log it, and re-read the shared storage slot first: if another
        // tab already holds a rotated live session, adopt it instead of dropping.
        // eslint-disable-next-line no-console
        console.warn('[auth] SIGNED_OUT event received — confirming against the stored session before leaving');
        void (async () => {
          let stored: any = null;
          try { stored = (await supabase.auth.getSession())?.data?.session ?? null; } catch { /* treat as gone */ }
          if (disposed) return;
          if (stored?.user) {
            // eslint-disable-next-line no-console
            console.warn('[auth] SIGNED_OUT ignored: a live session is still stored (rotated by another tab)');
            setUser(stored.user);
          } else {
            // eslint-disable-next-line no-console
            console.warn('[auth] SIGNED_OUT confirmed: no stored session — returning to Landing');
            setUser(null);
          }
        })();
        return;
      }
      setUser(session?.user ?? null);
    });

    const onVisible = () => {
      if (document.visibilityState === 'visible') void verify();
    };
    document.addEventListener('visibilitychange', onVisible);

    return () => {
      disposed = true;
      document.removeEventListener('visibilitychange', onVisible);
      subscription.unsubscribe();
    };
  }, [supabase, setUser, setInitialized]);
}

// ---------------------------------------------------------------------------
// Session-cookie auth (Wave-3, platform-auth-modernization)
// ---------------------------------------------------------------------------
//
// HttpOnly-cookie session-based auth — paired with the backend's
// `/api/auth/{login,me,logout}` triplet. The FE never sees the session
// token; the browser attaches `nai_session` automatically when fetch
// is called with `credentials: 'include'`.
//
// Why dual-mode at the seed level: other products keep the legacy
// localStorage/Supabase-JS path during the transition. The two shapes
// ship side-by-side and consumers (product Login.tsx + AuthProvider)
// pick which to call. Default-OFF: a product that imports nothing new
// keeps its Supabase flow.

/** Minimal user shape returned by `/api/auth/me` + `/api/auth/login`. */
export interface SessionUser {
  id: string;
  email: string;
}

/** Minimal org shape returned by `/api/auth/me` + `/api/auth/login`. */
export interface SessionOrg {
  id: string;
  name: string;
}

/** Response payload of `/api/auth/me` and `/api/auth/login`. */
export interface SessionAuthData {
  user: SessionUser;
  org: SessionOrg;
}

/**
 * Boot-time session restore — GET `/api/auth/me`.
 *
 * Mirrors `useSupabaseAuthInit` shape so it slots into the same
 * AuthProvider seam (`{ setUser, setInitialized }`). 200 → setUser
 * with the user payload; 401 → setUser(null); either resolves
 * `markAuthReady()` so data hooks gated on it stop deferring.
 *
 * Subscription / onAuthStateChange is deliberately absent — the
 * session lives server-side, so the FE has no equivalent of
 * Supabase's onAuthStateChange. `loginWithSession` / `logoutSession`
 * are the only state transitions; consumers call them and update the
 * store directly.
 */
export function useSessionAuthInit(
  setUser: (user: SessionUser | null) => void,
  setInitialized?: () => void,
) {
  useEffect(() => {
    if (env.DEV_AUTOLOGIN) {
      // Loud, unmissable — must never ship to prod unnoticed.
      // eslint-disable-next-line no-console
      console.warn(
        '%c[DEV AUTOLOGIN]%c synthetic session active as dev@noctusai.local — ' +
          'this MUST be off in production (VITE_DEV_AUTOLOGIN).',
        'background:#b91c1c;color:#fff;padding:2px 6px;border-radius:3px',
        'color:#b91c1c',
      );
      const u = devAutologinUser();
      setUser({ id: u.id, email: u.email ?? '' });
      setInitialized?.();
      markAuthReady();
      return;
    }

    let cancelled = false;
    void resolveBootVerdict<SessionUser>(
      async () => {
        try {
          const res = await fetch('/api/auth/me', {
            method: 'GET',
            credentials: 'include',
            headers: { Accept: 'application/json' },
          });
          const kind = classifyBootMeStatus(res.status);
          if (kind === 'ok') {
            const data: SessionAuthData = await res.json();
            return { kind: 'user', user: data.user };
          }
          // 401/403 is the expected "no session" path; 5xx/52x/408/429 is the
          // edge or backend mid-swap -- transient, never "signed out".
          return { kind };
        } catch {
          return { kind: 'transient' }; // no response (network drop / timeout)
        }
      },
      () => cancelled,
    ).then((verdict) => {
      if (!verdict) return;
      setUser(verdict.kind === 'user' ? verdict.user : null);
      setInitialized?.();
      markAuthReady();
    });

    return () => {
      cancelled = true;
    };
  }, [setUser, setInitialized]);
}

/**
 * POST `/api/auth/login` — submits credentials, browser stores the
 * resulting HttpOnly cookie. Returns the `{ user, org }` payload on
 * success; throws an `Error` with the server-supplied detail (or a
 * generic message) on 401 / network failure.
 *
 * The caller is responsible for pushing the returned user into its
 * auth store. This helper does not touch any module-level state.
 */
export async function loginWithSession(
  credentials: { email: string; password: string },
): Promise<SessionAuthData> {
  const res = await fetch('/api/auth/login', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(credentials),
  });
  if (!res.ok) {
    let detail = 'invalid credentials';
    try {
      const body = await res.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      // Non-JSON error body — fall back to the default detail.
    }
    throw new Error(detail);
  }
  return (await res.json()) as SessionAuthData;
}

/**
 * POST `/api/auth/logout` — deletes the session cookie server-side
 * (the response Set-Cookie clears it). Resolves on 204; throws on
 * non-2xx (so callers can surface failure if needed).
 */
export async function logoutSession(): Promise<void> {
  const res = await fetch('/api/auth/logout', {
    method: 'POST',
    credentials: 'include',
  });
  if (!res.ok) {
    throw new Error(`logout failed: ${res.status}`);
  }
}
