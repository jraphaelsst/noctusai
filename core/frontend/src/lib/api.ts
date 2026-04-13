/**
 * NoctusAI Core -- API Client (powered by shared factory)
 */
import { createApiClient } from '@noctusai/shared/api';

const API_URL = import.meta.env.VITE_CORE_API_URL || 'http://localhost:8000';

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
