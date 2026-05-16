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
