import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { api, clearToken, setToken, isAuthenticated, refreshCoreSession } from './api';
import { MfaChallengeHost } from '@noctusai/lib/components';
import { useActivityRefresh } from '@noctusai/lib/design-system/useActivityRefresh';
import { signOutExplicitly } from '@noctusai/lib/auth';

interface User {
  id: string;
  nome: string;
  email: string;
  role: string;
  org_id: string;
  avatar_url?: string;
}

interface Organization {
  id: string;
  nome: string;
  slug: string;
  plano: string;
  category?: string;
}

interface AuthState {
  user: User | null;
  organization: Organization | null;
  isAdmin: boolean;
  /**
   * `role === 'marketing'` — the website-only admin role (contract
   * `15-api-contract.md` §1/§6). Exposed alongside `isAdmin` so consumers
   * (the `CoreLayout` route gate, the `Layout` sidebar) branch on a stable
   * boolean instead of re-deriving `user?.role === 'marketing'` themselves.
   */
  isMarketing: boolean;
  loading: boolean;
  /**
   * `/api/auth/me` could not be reached (deploy restart, 5xx, Cloudflare 52x,
   * network) while the stored session is still held. The session is KEPT —
   * consumers show a retry state, never redirect to /login (2026-10-10: a
   * core redeploy logged every user out through a bare `catch → logout`).
   */
  unavailable: boolean;
}

interface AuthContextType extends AuthState {
  /**
   * Ends the session everywhere. Default: local state is cleared even if the
   * server revocation fails. `{ strict: true }` (used by /login before signing
   * in a different identity): a failed revocation THROWS and local state is kept
   * -- never sign out on an auth-server outage, never proceed on a half-revoked one.
   */
  logout: (opts?: { strict?: boolean }) => Promise<void>;
  /**
   * Ends the session in THIS browser only, with no server call -- for endings the
   * user did not ask for (inactivity expiry). Never revokes anything upstream.
   */
  endLocally: () => void;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  organization: null,
  isAdmin: false,
  isMarketing: false,
  loading: true,
  unavailable: false,
  logout: async () => {},
  endLocally: () => {},
  refresh: async () => {},
});

/** Backoff while `/api/auth/me` is unreachable (~30 s covers a redeploy). */
export const PROFILE_RETRY_DELAYS_MS = [1000, 2000, 4000, 8000, 15000];
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    organization: null,
    isAdmin: false,
    isMarketing: false,
    loading: true,
    unavailable: false,
  });

  async function fetchProfile() {
    if (!isAuthenticated()) {
      setState({ user: null, organization: null, isAdmin: false, isMarketing: false, loading: false, unavailable: false });
      return;
    }

    for (let attempt = 0; ; attempt++) {
      try {
        const data = await api.get('/api/auth/me');
        setState({
          user: data.user,
          organization: data.organization,
          isAdmin: data.user?.role === 'admin',
          isMarketing: data.user?.role === 'marketing',
          loading: false,
          unavailable: false,
        });
        return;
      } catch {
        // An authoritative 401 already went through the api client's
        // `onUnauthenticated` seam (lib/api.ts), which cleared the tokens and
        // redirected. A token STILL held here means the failure was transient
        // (deploy restart, 5xx, 52x, network): keep the session and retry.
        if (!isAuthenticated()) {
          setState({ user: null, organization: null, isAdmin: false, isMarketing: false, loading: false, unavailable: false });
          return;
        }
        if (attempt >= PROFILE_RETRY_DELAYS_MS.length) {
          setState((s) => ({ ...s, loading: false, unavailable: true }));
          return;
        }
        await sleep(PROFILE_RETRY_DELAYS_MS[attempt]);
      }
    }
  }

  useEffect(() => {
    // Handle OAuth callback: check URL hash for access_token
    handleOAuthCallback().then(() => fetchProfile());
  }, []);

  async function handleOAuthCallback() {
    const hash = window.location.hash;
    if (!hash) return;

    // Parse hash fragment: #access_token=...&token_type=...&...
    const params = new URLSearchParams(hash.substring(1));
    const accessToken = params.get('access_token');

    if (!accessToken) return;

    // Clean up the URL hash
    window.history.replaceState(null, '', window.location.pathname + window.location.search);

    // Store the token
    setToken(accessToken);

    // Ensure noctus_users profile exists via OAuth callback
    try {
      // Determine provider from URL params or default to 'google'
      const provider = params.get('provider') || 'google';
      await api.post('/api/auth/oauth/callback', { provider });
    } catch {
      // Profile creation failed, but token is set — fetchProfile will handle it
    }
  }

  function clearLocalSession() {
    clearToken();
    setState({ user: null, organization: null, isAdmin: false, isMarketing: false, loading: false, unavailable: false });
  }

  // The explicit "Sair" ONLY: core logout ends the user's sessions EVERYWHERE
  // (owner decision 2026-10-09) -- the server revokes first (it needs the bearer),
  // then local state is cleared regardless of the outcome. Endings the user did
  // not ask for (inactivity, a refused refresh) use `endLocally` and never reach
  // the server: 2026-10-23 a background core tab's timer called the global logout;
  // 2026-10-24 its `scope=local` successor still revoked server-side the session
  // every other core tab shares. See `@noctusai/lib/auth` `signOutExplicitly`.
  async function logout(opts?: { strict?: boolean }) {
    await signOutExplicitly({
      revoke: async () => { if (isAuthenticated()) await api.post('/api/auth/logout?scope=global', {}); },
      clearLocal: clearLocalSession,
      strict: opts?.strict,
      onRevokeError: (err) => console.error('core logout: server-side revocation failed; clearing local session anyway', err),
    });
  }

  // Expiry: this tab's state + the origin slot (the inactivity timer is shared by
  // every core tab, so it only fires when all of them are idle). No server call.
  function endLocally() {
    clearLocalSession();
  }

  // Proactive token refresh while user is active (every 5 min)
  // Same single, cross-tab-locked refresh the api client uses (lib/api.ts).
  const handleTokenRefresh = useCallback(async () => {
    try {
      await refreshCoreSession();
    } catch {
      // Refused or unavailable — the api client's 401 path decides on the next call.
    }
  }, []);

  useActivityRefresh({
    onRefresh: handleTokenRefresh,
    enabled: !!state.user,
  });

  return (
    <AuthContext.Provider value={{ ...state, logout, endLocally, refresh: fetchProfile }}>
      {children}
      {/* Step-up dialog for `403 mfa_required` from the api client (platform-admin-mfa). */}
      <MfaChallengeHost />
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
