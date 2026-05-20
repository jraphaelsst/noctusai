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

    supabase.auth.getSession().then(({ data: { session } }: { data: { session: any } }) => {
      setUser(session?.user ?? null);
      setInitialized?.();
      markAuthReady();
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event: any, session: any) => {
      setUser(session?.user ?? null);
    });

    return () => subscription.unsubscribe();
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
    fetch('/api/auth/me', {
      method: 'GET',
      credentials: 'include',
      headers: { Accept: 'application/json' },
    })
      .then(async (res) => {
        if (cancelled) return;
        if (res.ok) {
          const data: SessionAuthData = await res.json();
          setUser(data.user);
        } else {
          // 401 (auth required) is the expected "no session" path; any
          // other error also collapses to "no user" so the UI renders
          // the Landing/Login flow rather than spinning forever.
          setUser(null);
        }
      })
      .catch(() => {
        // Network failure: treat as "no session" so the boot completes.
        // The user can retry login; data hooks gating on `useAuthReady`
        // stop deferring.
        if (!cancelled) setUser(null);
      })
      .finally(() => {
        if (cancelled) return;
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
