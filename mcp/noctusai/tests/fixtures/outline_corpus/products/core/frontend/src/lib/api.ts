/**
 * NoctusAI Core -- API Client (powered by shared factory)
 */
import { createApiClient } from '@noctusai/lib/api';

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
 * Refresh the access token via core's stored refresh token. Raw `fetch`
 * (not the `api`/`client` object being constructed below) — routing this
 * through the client would re-enter `onTokenExpired` if the refresh call
 * itself 401s.
 */
async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return null;
  try {
    const response = await fetch(`${API_URL}/api/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!response.ok) return null;
    const data = await response.json();
    if (!data.access_token) return null;
    setToken(data.access_token);
    if (data.refresh_token) setRefreshToken(data.refresh_token);
    return data.access_token;
  } catch {
    return null;
  }
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

const client = createApiClient({
  getBaseUrl: () => API_URL,
  getAuthToken: async () => getToken(),
  onTokenExpired: refreshAccessToken,
  onUnauthenticated: handleDeadSession,
});

export const api = client;

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
