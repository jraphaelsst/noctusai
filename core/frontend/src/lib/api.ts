/**
 * NoctusAI Core — API Client
 */
const API_URL = import.meta.env.VITE_CORE_API_URL || 'http://localhost:8000';

function getToken(): string | null {
  return localStorage.getItem('noctus_token');
}

function extractErrorMessage(data: any, status: number): string {
  if (data?.error?.message) return data.error.message;
  if (data?.detail) {
    if (typeof data.detail === 'string') return data.detail;
    if (Array.isArray(data.detail)) {
      return data.detail.map((e: any) => e.msg || e.message).join('; ');
    }
  }
  if (data?.message) return data.message;
  return `Erro HTTP ${status}`;
}

async function request(method: string, path: string, body?: any) {
  const token = getToken();
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error(`Servidor indisponível (${path}). Verifique se o backend está rodando.`);
  }

  if (!res.ok) {
    const data = await res.json().catch(() => null);
    const message = data ? extractErrorMessage(data, res.status) : `Erro HTTP ${res.status}`;
    throw new Error(`[${res.status}] ${message}`);
  }
  return res.json();
}

export const api = {
  get: (path: string) => request('GET', path),
  post: (path: string, body?: any) => request('POST', path, body),
  put: (path: string, body?: any) => request('PUT', path, body),
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
