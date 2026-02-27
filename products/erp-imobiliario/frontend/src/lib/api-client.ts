/**
 * Centralized API client for the frontend.
 * All data operations go through the FastAPI backend.
 * The only direct Supabase usage is for auth (login/signup/session).
 */
import { supabase } from '@/integrations/supabase/client';

const BACKEND_URL = import.meta.env.VITE_BACKEND_API_URL || 'http://localhost:8001';

async function getAuthHeaders(): Promise<Record<string, string>> {
  const { data: { session } } = await supabase.auth.getSession();
  if (!session?.access_token) {
    throw new Error('Não autenticado');
  }
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${session.access_token}`,
  };
}

async function handleResponse(response: Response) {
  if (!response.ok) {
    const error = await response.json().catch(() => ({
      detail: `Request failed with status ${response.status}`,
    }));
    throw new Error(error.detail || error.error || 'Erro na requisição');
  }
  return response.json();
}

export const api = {
  async get<T = any>(path: string, params?: Record<string, any>): Promise<T> {
    const headers = await getAuthHeaders();
    const url = new URL(`${BACKEND_URL}${path}`);
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') {
          url.searchParams.set(key, String(value));
        }
      });
    }
    const response = await fetch(url.toString(), { headers });
    return handleResponse(response);
  },

  async post<T = any>(path: string, body?: any): Promise<T> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${BACKEND_URL}${path}`, {
      method: 'POST',
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
    return handleResponse(response);
  },

  async patch<T = any>(path: string, body?: any): Promise<T> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${BACKEND_URL}${path}`, {
      method: 'PATCH',
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
    return handleResponse(response);
  },

  async delete<T = any>(path: string): Promise<T> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${BACKEND_URL}${path}`, {
      method: 'DELETE',
      headers,
    });
    return handleResponse(response);
  },
};
