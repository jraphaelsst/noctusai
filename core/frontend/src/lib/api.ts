/**
 * NoctusAI Core — API Client
 */
const API_URL = import.meta.env.VITE_CORE_API_URL || 'http://localhost:8001';

function getToken(): string | null {
  return localStorage.getItem('noctus_token');
}

async function request(method: string, path: string, body?: any) {
  const token = getToken();
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${API_URL}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `Erro ${res.status}` }));
    throw new Error(err.detail || 'Erro na requisição');
  }
  return res.json();
}

export const api = {
  get: (path: string) => request('GET', path),
  post: (path: string, body?: any) => request('POST', path, body),
  patch: (path: string, body?: any) => request('PATCH', path, body),
  delete: (path: string) => request('DELETE', path),
};

export function setToken(token: string) {
  localStorage.setItem('noctus_token', token);
}

export function clearToken() {
  localStorage.removeItem('noctus_token');
}

export function isAuthenticated(): boolean {
  return !!getToken();
}
