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

/**
 * Error thrown by the API client, carrying the HTTP status as a STRUCTURED
 * field so consumers branch on `err.status` (409/422/424/502 UX) instead of
 * regex-parsing the message prefix. The message keeps the historical
 * `[<status>] <message>` shape for backward compatibility — every existing
 * consumer reading `err.message` (and the `/^\[(\d+)\]/` parsers products
 * hand-rolled before this field existed) keeps working unchanged.
 *
 * `status` is `null` for a transport-level failure (server unreachable) that
 * never produced an HTTP response — an honest "there is no status", never 0.
 */
export class ApiError extends Error {
  readonly status: number | null;
  constructor(status: number | null, message: string) {
    super(status === null ? message : `[${status}] ${message}`);
    this.name = 'ApiError';
    this.status = status;
    // Restore prototype chain — required when extending built-ins under the
    // TS `target` this lib compiles to, so `err instanceof ApiError` holds.
    Object.setPrototypeOf(this, ApiError.prototype);
  }
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ApiClient {
  get<T = any>(path: string, params?: Record<string, any>): Promise<T>;
  post<T = any>(path: string, body?: unknown): Promise<T>;
  patch<T = any>(path: string, body?: unknown): Promise<T>;
  put<T = any>(path: string, body?: unknown): Promise<T>;
  /**
   * DELETE, optionally with a JSON body.
   *
   * A body on DELETE is legal HTTP and FastAPI routes do declare one — e.g.
   * `DELETE /api/email-marketing/lists/{id}/members` takes `{contact_ids}`.
   * Without this parameter such a route is simply unreachable from any
   * product, which is how it went unwired. Optional and body-less by default,
   * so every existing `api.delete(path)` call is unaffected.
   */
  delete<T = any>(path: string, body?: unknown): Promise<T>;
  /**
   * POST `multipart/form-data`. Use for ANY endpoint taking `UploadFile`.
   *
   * A separate method rather than letting `post` detect FormData, because the
   * silent-failure mode is what makes this worth a distinct name: `post`
   * JSON.stringify's its body, and `JSON.stringify(new FormData())` is `"{}"`.
   * So passing FormData to `post` sends an EMPTY JSON object with
   * `Content-Type: application/json` to a multipart endpoint — no type error,
   * no console warning, just a 422 that reads like a backend bug. Found live
   * in `adconnect`'s two sellout uploads (2026-09-01), which had been sending
   * `{}` this whole time.
   */
  upload<T = any>(path: string, form: FormData): Promise<T>;
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
  /**
   * Called when a 401 could NOT be recovered — there was no token to send, OR
   * `onTokenExpired` returned null / the retried request still 401'd. The session
   * is dead: the server has rejected auth and no refresh restored it. The product
   * should clear its auth state + redirect to login instead of leaving the user
   * stranded on a shell that 401s every call ("[401] Token ausente" on every
   * page). Invoked at most conceptually-once per dead session (the product's
   * handler should be idempotent / re-entrancy-guarded, since many concurrent
   * requests can 401 together). The 401 is still propagated to the caller.
   */
  onUnauthenticated?: () => void;
}

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

export function createApiClient(options: CreateApiClientOptions): ApiClient {
  const { getBaseUrl, getAuthToken, onTokenExpired, onUnauthenticated } = options;

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
      throw new ApiError(response.status, message);
    }
    if (response.status === 204) return null as T;
    // 200 OK with non-JSON body is the classic SPA-fallback-eats-API shape
    // (proxy mis-route, container drift, FE/BE version skew). The seed
    // _SPAStaticFiles carve-out (`/api/*` returns real 404) cures the
    // primary cause, but proxy edges still produce this — turn the raw
    // JS engine SyntaxError ("Unexpected token '<', '<!doctype ...' is
    // not valid JSON") into a typed error that names what's actually wrong.
    try {
      return await response.json();
    } catch (err) {
      const path = new URL(response.url).pathname;
      const ct = response.headers.get('content-type') || 'unknown';
      throw new ApiError(
        response.status,
        `Resposta nao-JSON em ${path} ` +
        `(content-type=${ct}). Provavel: deploy desatualizado ou ` +
        `descompasso FE/BE — verifique se a rota existe na imagem ativa.`,
      );
    }
  }

  async function safeFetch(url: string, init: RequestInit): Promise<Response> {
    try {
      return await fetch(url, init);
    } catch {
      const path = new URL(url).pathname;
      throw new ApiError(null, `Servidor indisponivel (${path}). Verifique se o backend esta rodando.`);
    }
  }

  /**
   * Execute a fetch request. On a 401: if `onTokenExpired` is configured, force a
   * token refresh and retry exactly once. If the 401 cannot be recovered (no
   * refresh, refresh returned null, or the retry ALSO 401'd), the session is dead
   * → signal `onUnauthenticated` so the product bounces to login instead of
   * stranding the user on a shell that 401s every call. The 401 is still returned
   * (and thrown by `handleResponse`), but the redirect will already be in flight.
   */
  async function fetchWithRetry(url: string, init: RequestInit): Promise<Response> {
    const response = await safeFetch(url, init);
    if (response.status !== 401) return response;

    if (onTokenExpired) {
      const freshToken = await onTokenExpired();
      if (freshToken) {
        const retryHeaders = { ...init.headers as Record<string, string> };
        retryHeaders['Authorization'] = `Bearer ${freshToken}`;
        const retry = await safeFetch(url, { ...init, headers: retryHeaders });
        if (retry.status !== 401) return retry;
        // refresh produced a token the server STILL rejects → session is dead.
      }
    }

    // Unrecoverable 401 — the session is dead. Tell the product to log out +
    // redirect (idempotent handler; concurrent 401s collapse to one redirect).
    onUnauthenticated?.();
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

    async upload<T = any>(path: string, form: FormData): Promise<T> {
      // Auth header only — the Content-Type is DELIBERATELY omitted so the
      // browser sets `multipart/form-data; boundary=…` itself. Setting it by
      // hand produces a boundary-less header and the server cannot parse the
      // parts.
      const headers = await buildHeaders();
      delete headers['Content-Type'];
      const base = getBaseUrl();
      const response = await fetchWithRetry(`${base}${path}`, {
        method: 'POST',
        headers,
        body: form,
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

    async delete<T = any>(path: string, body?: unknown): Promise<T> {
      const headers = await buildHeaders();
      const base = getBaseUrl();
      const response = await fetchWithRetry(`${base}${path}`, {
        method: 'DELETE',
        headers,
        body: body ? JSON.stringify(body) : undefined,
      });
      return handleResponse<T>(response);
    },
  };
}
