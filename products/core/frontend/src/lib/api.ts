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

const client = createApiClient({
  getBaseUrl: () => API_URL,
  getAuthToken: async () => getToken(),
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
