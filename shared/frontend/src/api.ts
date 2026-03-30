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
  /**
   * Called when a request receives a 401 response. Should force a session
   * refresh and return a fresh token, or `null` if refresh failed.
   * When provided, the client automatically retries the failed request once
   * with the new token before propagating the error.
   */
  onTokenExpired?: () => Promise<string | null>;
}

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

export function createApiClient(options: CreateApiClientOptions): ApiClient {
  const { getBaseUrl, getAuthToken, onTokenExpired } = options;

  async function buildHeaders(token?: string | null): Promise<Record<string, string>> {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    const t = token ?? await getAuthToken();
    if (t) {
      headers['Authorization'] = `Bearer ${t}`;
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

  /**
   * Execute a fetch request. If the response is 401 and `onTokenExpired` is
   * configured, force a token refresh and retry the request exactly once.
   */
  async function fetchWithRetry(url: string, init: RequestInit): Promise<Response> {
    const response = await safeFetch(url, init);

    if (response.status === 401 && onTokenExpired) {
      const freshToken = await onTokenExpired();
      if (freshToken) {
        const retryHeaders = { ...init.headers as Record<string, string> };
        retryHeaders['Authorization'] = `Bearer ${freshToken}`;
        return safeFetch(url, { ...init, headers: retryHeaders });
      }
    }

    return response;
  }

  return {
    async get<T = any>(path: string, params?: Record<string, any>): Promise<T> {
      const headers = await buildHeaders();
      const base = getBaseUrl();
      const url = new URL(`${base}${path}`);
      if (params) {
        Object.entries(params).forEach(([key, value]) => {
          if (value !== undefined && value !== null && value !== '') {
            url.searchParams.set(key, String(value));
          }
        });
      }
      const response = await fetchWithRetry(url.toString(), { headers });
      return handleResponse<T>(response);
    },

    async post<T = any>(path: string, body?: unknown): Promise<T> {
      const headers = await buildHeaders();
      const base = getBaseUrl();
      const response = await fetchWithRetry(`${base}${path}`, {
        method: 'POST',
        headers,
        body: body ? JSON.stringify(body) : undefined,
      });
      return handleResponse<T>(response);
    },

    async patch<T = any>(path: string, body?: unknown): Promise<T> {
      const headers = await buildHeaders();
      const base = getBaseUrl();
      const response = await fetchWithRetry(`${base}${path}`, {
        method: 'PATCH',
        headers,
        body: body ? JSON.stringify(body) : undefined,
      });
      return handleResponse<T>(response);
    },

    async put<T = any>(path: string, body?: unknown): Promise<T> {
      const headers = await buildHeaders();
      const base = getBaseUrl();
      const response = await fetchWithRetry(`${base}${path}`, {
        method: 'PUT',
        headers,
        body: body ? JSON.stringify(body) : undefined,
      });
      return handleResponse<T>(response);
    },

    async delete<T = any>(path: string): Promise<T> {
      const headers = await buildHeaders();
      const base = getBaseUrl();
      const response = await fetchWithRetry(`${base}${path}`, {
        method: 'DELETE',
        headers,
      });
      return handleResponse<T>(response);
    },
  };
}
