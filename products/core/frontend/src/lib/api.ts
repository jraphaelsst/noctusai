/**
 * NoctusAI Core -- API Client (powered by shared factory)
 */
import {
  createApiClient,
  isTransientHttpStatus,
  refreshWithBackoff,
  type RefreshAttempt,
} from '@noctusai/lib/api';
import type { MfaVerifyResult } from '@noctusai/lib';

// core's API is SAME-ORIGIN (single-container house model serves FE + API on
// one host). Default to window.location.origin so core is deploy-host-agnostic
// — no baked URL needed for its own backend. VITE_CORE_API_URL stays as an
// explicit override for the rare split-origin core. (The cross-product "reach
// core" URL is VITE_CORE_URL, used by OTHER products' SSO/nav — not this.)
const API_URL =
  import.meta.env.VITE_CORE_API_URL ||
  (typeof window !== 'undefined' ? window.location.origin : 'http://localhost:8000');

function getToken(): string | null {
  return localStorage.getItem('noctus_token');
}

// Re-entrancy guard: a burst of concurrent 401s on one dead session must
// collapse to ONE redirect, not one per in-flight request (mirrors the
// seed's own `handleDeadSession` in `seed/framework/frontend/src/infra.tsx`).
let _handlingDeadSession = false;

/**
 * ONE refresh attempt via core's stored refresh token, classified. Raw `fetch`
 * (not the `api`/`client` object being constructed below) — routing this
 * through the client would re-enter `onTokenExpired` if the refresh call
 * itself 401s.
 *
 * Only an ANSWERED 4xx from `/api/auth/refresh` (core answers 401 only when
 * Supabase refused the refresh token) means the session is dead. A network
 * error, a 5xx, a Cloudflare 52x (the tunnel restarts on every deploy) or a
 * 429 is transient — `refreshWithBackoff` retries it and, if it persists,
 * throws `TransientAuthError`, which the api client treats as "keep the
 * session". Treating both as "dead" logged the owner out after prod deploys
 * (2026-10-03).
 */
async function refreshAttempt(): Promise<RefreshAttempt> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return { kind: 'dead' };
  let response: Response;
  try {
    response = await fetch(`${API_URL}/api/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
  } catch (err) {
    return { kind: 'transient', reason: err instanceof Error ? err.message : 'network error' };
  }
  if (isTransientHttpStatus(response.status)) {
    return { kind: 'transient', reason: `HTTP ${response.status}` };
  }
  if (!response.ok) return { kind: 'dead' };
  const data = await response.json().catch(() => null);
  if (!data?.access_token) {
    // A 2xx without a token is not an authoritative refusal (e.g. an edge
    // serving an HTML page) — do not log out on it.
    return { kind: 'transient', reason: 'refresh answered without a token' };
  }
  setToken(data.access_token);
  if (data.refresh_token) setRefreshToken(data.refresh_token);
  return { kind: 'token', token: data.access_token };
}

/** `onTokenExpired`: token | null (refused → dead) | throws (unanswered → keep). */
function refreshAccessToken(): Promise<string | null> {
  return refreshWithBackoff(refreshAttempt);
}

/**
 * Dead session: the server rejected auth and refresh couldn't recover it.
 * Clear stored tokens + bounce to `/login` instead of stranding the user on
 * a shell where every subsequent call 401s. Never redirects while already
 * on `/login` (no loop); re-entrancy-guarded so concurrent 401s collapse to
 * one redirect. Guard resets after a few seconds so a LATER genuine dead
 * session (re-login → expiry again) can still redirect.
 */
function handleDeadSession(): void {
  if (_handlingDeadSession) return;
  if (typeof window === 'undefined' || window.location.pathname.startsWith('/login')) return;
  _handlingDeadSession = true;
  clearToken();
  window.location.assign('/login');
  window.setTimeout(() => { _handlingDeadSession = false; }, 3000);
}

/**
 * Step-up (`403 mfa_required` -> `MfaChallengeDialog` -> `/api/auth/mfa/verify`)
 * returns aal2 tokens for a Bearer SPA; swap them in BEFORE the api client
 * retries the blocked request (platform-admin-mfa M4 `onMfaVerified` seam).
 */
export function storeMfaTokens(result: MfaVerifyResult): void {
  if (result.access_token) setToken(result.access_token);
  if (result.refresh_token) setRefreshToken(result.refresh_token);
}

const client = createApiClient({
  getBaseUrl: () => API_URL,
  getAuthToken: async () => getToken(),
  onTokenExpired: refreshAccessToken,
  onUnauthenticated: handleDeadSession,
  onMfaVerified: storeMfaTokens,
});

export const api = client;

/**
 * Transport for the LOGIN challenge: sends the pending aal1 token (which is NOT
 * stored yet) as Bearer to the seed `/api/auth/mfa/*` router. No refresh /
 * dead-session handlers and no step-up interceptor hooks: a 401 or 403 here is
 * a plain error for the dialog to show, never a redirect.
 */
export function createLoginMfaTransport(pendingAccessToken: string) {
  return createApiClient({
    getBaseUrl: () => API_URL,
    getAuthToken: async () => pendingAccessToken,
  });
}

export function setToken(token: string) {
  localStorage.setItem('noctus_token', token);
}

export function setRefreshToken(token: string) {
  localStorage.setItem('noctus_refresh_token', token);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem('noctus_refresh_token');
}

export function clearToken() {
  localStorage.removeItem('noctus_token');
  localStorage.removeItem('noctus_refresh_token');
}

export function isAuthenticated(): boolean {
  return !!getToken();
}
