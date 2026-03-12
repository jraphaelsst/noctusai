/**
 * Shared API client factory for NoctusAI products.
 *
 * Each product provides its own `getBaseUrl` and `getAuthToken` callbacks
 * so the fetch logic (error extraction, safe fetch, response handling)
 * is written once.
 */

// ---------------------------------------------------------------------------
// Error extraction — identical across all three frontends
// ---------------------------------------------------------------------------

export function extractErrorMessage(data: any, status: number): string {
  // Backend returns { error: { code, message } }
  if (data?.error?.message) return data.error.message;
  // FastAPI default format
  if (data?.detail) {
    if (typeof data.detail === 'string') return data.detail;
    // Pydantic validation errors: [{loc, msg, type}]
    if (Array.isArray(data.detail)) {
      return data.detail.map((e: any) => e.msg || e.message).join('; ');
    }
  }
  if (data?.message) return data.message;
  return `Erro HTTP ${status}`;
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ApiClient {
  get<T = any>(path: string, params?: Record<string, any>): Promise<T>;
  post<T = any>(path: string, body?: unknown): Promise<T>;
  patch<T = any>(path: string, body?: unknown): Promise<T>;
  put<T = any>(path: string, body?: unknown): Promise<T>;
  delete<T = any>(path: string): Promise<T>;
}

export interface CreateApiClientOptions {
  /** Returns the backend base URL (e.g. `http://localhost:8001`). */
  getBaseUrl: () => string;
  /**
   * Returns the current auth token, or `null` if unauthenticated.
   * When `null` is returned the request is still sent (without Authorization header)
   * — useful for public endpoints. If the product requires strict auth, the
   * callback should throw instead.
   */
  getAuthToken: () => Promise<string | null>;
}

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

export function createApiClient(options: CreateApiClientOptions): ApiClient {
  const { getBaseUrl, getAuthToken } = options;

  async function getHeaders(): Promise<Record<string, string>> {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    const token = await getAuthToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    return headers;
  }

  async function handleResponse<T>(response: Response): Promise<T> {
    if (!response.ok) {
      const data = await response.json().catch(() => null);
      const message = data
        ? extractErrorMessage(data, response.status)
        : `Erro HTTP ${response.status}`;
      throw new Error(`[${response.status}] ${message}`);
    }
    if (response.status === 204) return null as T;
    return response.json();
  }

  async function safeFetch(url: string, init: RequestInit): Promise<Response> {
    try {
      return await fetch(url, init);
    } catch {
      const path = new URL(url).pathname;
      throw new Error(`Servidor indisponivel (${path}). Verifique se o backend esta rodando.`);
    }
  }

  return {
    async get<T = any>(path: string, params?: Record<string, any>): Promise<T> {
      const headers = await getHeaders();
      const base = getBaseUrl();
      const url = new URL(`${base}${path}`);
      if (params) {
        Object.entries(params).forEach(([key, value]) => {
          if (value !== undefined && value !== null && value !== '') {
            url.searchParams.set(key, String(value));
          }
        });
      }
      const response = await safeFetch(url.toString(), { headers });
      return handleResponse<T>(response);
    },

    async post<T = any>(path: string, body?: unknown): Promise<T> {
      const headers = await getHeaders();
      const base = getBaseUrl();
      const response = await safeFetch(`${base}${path}`, {
        method: 'POST',
        headers,
        body: body ? JSON.stringify(body) : undefined,
      });
      return handleResponse<T>(response);
    },

    async patch<T = any>(path: string, body?: unknown): Promise<T> {
      const headers = await getHeaders();
      const base = getBaseUrl();
      const response = await safeFetch(`${base}${path}`, {
        method: 'PATCH',
        headers,
        body: body ? JSON.stringify(body) : undefined,
      });
      return handleResponse<T>(response);
    },

    async put<T = any>(path: string, body?: unknown): Promise<T> {
      const headers = await getHeaders();
      const base = getBaseUrl();
      const response = await safeFetch(`${base}${path}`, {
        method: 'PUT',
        headers,
        body: body ? JSON.stringify(body) : undefined,
      });
      return handleResponse<T>(response);
    },

    async delete<T = any>(path: string): Promise<T> {
      const headers = await getHeaders();
      const base = getBaseUrl();
      const response = await safeFetch(`${base}${path}`, {
        method: 'DELETE',
        headers,
      });
      return handleResponse<T>(response);
    },
  };
}
