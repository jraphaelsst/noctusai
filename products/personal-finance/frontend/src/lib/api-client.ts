import { supabase } from "@/integrations/supabase/client";

const BACKEND_URL = import.meta.env.VITE_BACKEND_API_URL || "http://localhost:8002";

async function getAuthHeaders(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const token = data?.session?.access_token;
  return token
    ? { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }
    : { "Content-Type": "application/json" };
}

function extractErrorMessage(data: any, status: number): string {
  if (data?.error?.message) return data.error.message;
  if (data?.detail) {
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) {
      return data.detail.map((e: any) => e.msg || e.message).join("; ");
    }
  }
  if (data?.message) return data.message;
  return `Erro HTTP ${status}`;
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    const message = data ? extractErrorMessage(data, response.status) : `Erro HTTP ${response.status}`;
    throw new Error(`[${response.status}] ${message}`);
  }
  return response.json();
}

async function safeFetch(path: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(`${BACKEND_URL}${path}`, init);
  } catch {
    throw new Error(`Servidor indisponível (${path}). Verifique se o backend está rodando.`);
  }
}

export const api = {
  async get<T = any>(path: string, params?: Record<string, any>): Promise<T> {
    const headers = await getAuthHeaders();
    const url = new URL(`${BACKEND_URL}${path}`);
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== "") {
          url.searchParams.set(key, String(value));
        }
      });
    }
    try {
      const response = await fetch(url.toString(), { headers });
      return handleResponse<T>(response);
    } catch (err) {
      if (err instanceof Error && err.message.startsWith("[")) throw err;
      throw new Error(`Servidor indisponível (${path}). Verifique se o backend está rodando.`);
    }
  },

  async post<T = any>(path: string, body?: any): Promise<T> {
    const headers = await getAuthHeaders();
    const response = await safeFetch(path, {
      method: "POST",
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
    return handleResponse<T>(response);
  },

  async patch<T = any>(path: string, body?: any): Promise<T> {
    const headers = await getAuthHeaders();
    const response = await safeFetch(path, {
      method: "PATCH",
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
    return handleResponse<T>(response);
  },

  async delete<T = any>(path: string): Promise<T> {
    const headers = await getAuthHeaders();
    const response = await safeFetch(path, {
      method: "DELETE",
      headers,
    });
    return handleResponse<T>(response);
  },
};
