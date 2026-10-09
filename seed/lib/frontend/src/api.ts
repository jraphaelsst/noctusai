/**
 * Shared API client factory for NoctusAI products.
 *
 * Each product provides its own `getBaseUrl` and `getAuthToken` callbacks
 * so the fetch logic (error extraction, safe fetch, response handling)
 * is written once.
 */

import { isOrgSelectionChangedBody, isOrgSemLicencaBody, redirectToSemAcesso } from './access';
import { ORG_PIN_HEADER, getOrgPin, notifyOrgSelectionChanged } from './org-pin';

// ---------------------------------------------------------------------------
// X-Noctus-Client — the caller-kind signal `AuditMiddleware`
// (`noctusai_lib.api.audit`) reads on the way in. `"web"` for a normal
// browser session; `"agent:webdriver"` when `navigator.webdriver` is
// true — the standard automation tell every headless-Chrome/Playwright/
// Selenium driver sets, present specifically because the driver IS
// automating a real browser (a plain script hitting fetch() directly
// has no `navigator` at all, which is exactly the case this constant
// itself guards against below).
// ---------------------------------------------------------------------------

export function detectNoctusClientHeader(): string {
  if (typeof navigator !== 'undefined' && (navigator as any).webdriver) {
    return 'agent:webdriver';
  }
  return 'web';
}

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
 * Parse an HTTP `Retry-After` header value into a whole number of seconds to
 * wait before retrying. The header is legal in TWO shapes (RFC 9110 §10.2.3):
 * delta-seconds (`"10"`) or an HTTP-date (`"Wed, 21 Oct 2026 07:28:00 GMT"`).
 * A date already in the past resolves to `0` (retry is allowed NOW — that is
 * information, not an error). Returns `null` for anything absent or that
 * parses as neither shape — callers must never invent a made-up countdown
 * for a header they could not actually read.
 */
export function parseRetryAfterSeconds(value: string | null | undefined): number | null {
  if (!value) return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (/^\d+$/.test(trimmed)) {
    const seconds = Number(trimmed);
    return Number.isFinite(seconds) ? seconds : null;
  }
  const dateMs = Date.parse(trimmed);
  if (Number.isNaN(dateMs)) return null;
  const deltaMs = dateMs - Date.now();
  return deltaMs > 0 ? Math.ceil(deltaMs / 1000) : 0;
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
 *
 * `body` is the parsed JSON error body (`undefined` when the response had
 * none or it was not JSON). Backends answer `{error: {code, message,
 * details}}`; `code` and `details` read straight from it, so a consumer that
 * needs the structured refusal — a field list, a conflict id — branches on
 * them instead of re-implementing the fetch to see the body the message
 * extraction used to discard.
 *
 * `retryAfterSeconds` is the response's `Retry-After` header, parsed via
 * `parseRetryAfterSeconds` — `null` when the response carried no such header
 * (or its own transport-level failure had no headers at all) or it did not
 * parse as delta-seconds/an HTTP-date. A 4th, OPTIONAL constructor
 * parameter — every pre-existing 2/3-arg call site (products' own tests
 * included) keeps constructing a valid `ApiError` with `retryAfterSeconds:
 * null`, unchanged.
 */
export class ApiError extends Error {
  readonly status: number | null;
  readonly body: unknown;
  readonly retryAfterSeconds: number | null;
  constructor(status: number | null, message: string, body?: unknown, retryAfterSeconds: number | null = null) {
    super(status === null ? message : `[${status}] ${message}`);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
    this.retryAfterSeconds = retryAfterSeconds;
    // Restore prototype chain — required when extending built-ins under the
    // TS `target` this lib compiles to, so `err instanceof ApiError` holds.
    Object.setPrototypeOf(this, ApiError.prototype);
  }

  /**
   * `error.code` from a `{error: {code, ...}}` body (nested shape), or `code`
   * from a `{detail, code}` body (flat shape) — or `null` if neither is a
   * string. Nested wins when a body somehow carries both.
   */
  get code(): string | null {
    const body = this.body as { error?: { code?: unknown }; code?: unknown } | undefined;
    const nested = body?.error?.code;
    if (typeof nested === 'string') return nested;
    const flat = body?.code;
    return typeof flat === 'string' ? flat : null;
  }

  /** `error.details` from a `{error: {details, ...}}` body, or `null`. */
  get details(): unknown {
    return (this.body as { error?: { details?: unknown } } | undefined)?.error?.details ?? null;
  }
}

import { mfaChallenge } from './mfaChallenge';
import type { MfaVerifyResult } from './mfaChallenge';

/** Base path of the seed `mfa` router (`standard_routers`). */
export const MFA_BASE_PATH = '/api/auth/mfa';

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
  /**
   * GET a binary response (e.g. a generated zip/PDF) as a `Blob`. Use for ANY
   * endpoint that doesn't return JSON — `get`'s response handling always
   * calls `response.json()`, which throws on binary content (the same class
   * of silent-shaped mismatch `upload` exists to prevent on the write side).
   * Shares the same auth header + 401-retry path as every other method; on a
   * non-2xx response it still extracts `{error:{code,message}}`/FastAPI
   * `detail` from the body when present, so a caller branching on
   * `err.status` (e.g. 409 "not ready yet") gets the same `ApiError` shape
   * every other method throws.
   */
  download(path: string): Promise<Blob>;
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
   * refresh and return a fresh token.
   *
   * The return/throw contract is load-bearing — it decides whether the user
   * gets logged out:
   *  - a token  → the failed request is retried once with it;
   *  - `null`   → the refresh endpoint AUTHORITATIVELY refused (invalid /
   *               revoked refresh token): the session is dead →
   *               `onUnauthenticated`;
   *  - throws   → the refresh could not get an answer (network error, 5xx,
   *               Cloudflare 52x during a deploy/tunnel restart, 429). That is
   *               NOT a dead session: the 401 propagates to the caller but
   *               `onUnauthenticated` is NOT called, so the user stays logged
   *               in. Throw `TransientAuthError` (see `refreshWithBackoff`,
   *               which retries transient failures before giving up).
   *
   * Concurrent 401s share ONE in-flight call (single-flight) — a page firing
   * ten requests on an expired token refreshes once, not ten times.
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
   *
   * NEVER called when `onTokenExpired` threw (refresh unanswered — see above):
   * a deploy's container swap / tunnel restart must not log anyone out.
   */
  onUnauthenticated?: () => void;
  /**
   * Admin step-up. When an admin call answers `403 {code:"mfa_required"}` the
   * client opens ONE `MfaChallengeDialog` (via `<MfaChallengeHost/>`, mounted
   * by the seed AuthProviders), then RETRIES the call once on success — or
   * throws the original 403 on cancel. Concurrent 403s share one dialog.
   *
   * `/api/auth/mfa/verify` returns fresh tokens for Bearer SPAs: hand them to
   * the storage this client already reads in `getAuthToken` (e.g. the Supabase
   * `setSession`). Cookie-session products need no handler. Awaited before the
   * retry so the retry carries the aal2 token.
   */
  onMfaVerified?: (result: MfaVerifyResult) => Promise<void> | void;
  /**
   * Called when any call answers `403 {code:"org_sem_licenca"}` (the org holds
   * no active license for this product). Defaults to a hard navigation to
   * `/sem-acesso`, which every product mounts via the seed shell.
   */
  onOrgSemLicenca?: () => void;
}

// ---------------------------------------------------------------------------
// Session refresh resilience — a deploy must never log a user out
// ---------------------------------------------------------------------------
//
// 2026-10-03: the owner was logged out of social.noctusai.com by three prod
// deploys in one day. A deploy swaps the product container AND restarts the
// cloudflared tunnel, so for a few seconds every request answers a Cloudflare
// 502/530 or fails at the network layer. The api client used to treat a
// refresh that could not get an answer exactly like a refresh that was
// REFUSED (`onTokenExpired` returned null for both) and logged the user out.
// The split below is the contract: only an authoritative refusal is "dead".

/**
 * Thrown by an `onTokenExpired` implementation when the refresh could not get
 * an authoritative answer (network error, 5xx, Cloudflare 52x, 429). The api
 * client keeps the session (no `onUnauthenticated`) and propagates the
 * original 401 to the caller.
 */
export class TransientAuthError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'TransientAuthError';
    Object.setPrototypeOf(this, TransientAuthError.prototype);
  }
}

/**
 * True for an HTTP status that means "try again", never "you are not logged
 * in": 0 (no response — fetch/network failure), 408, 425, 429, and every 5xx
 * (incl. Cloudflare's 520-530 origin/tunnel errors).
 */
export function isTransientHttpStatus(status: number | null | undefined): boolean {
  if (status === null || status === undefined || status === 0) return true;
  return status === 408 || status === 425 || status === 429 || status >= 500;
}

/** The result of ONE refresh attempt, as classified by the caller. */
export type RefreshAttempt =
  | { kind: 'token'; token: string }
  | { kind: 'dead' }
  | { kind: 'transient'; reason: string };

export interface RefreshWithBackoffOptions {
  /** Waits between attempts (ms). Default `[500, 1500, 4000]` → 4 attempts
   *  over ~6s — long enough to ride out a container swap + tunnel restart,
   *  short enough to stay inside Supabase's 10s refresh-token reuse window. */
  delaysMs?: number[];
  /** Injected for tests; defaults to `setTimeout`. */
  sleep?: (ms: number) => Promise<void>;
}

const defaultSleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/**
 * Run a refresh attempt, retrying TRANSIENT outcomes with backoff.
 *
 * Resolves the token, resolves `null` on the first authoritative refusal
 * (`dead` — never retried: a revoked token stays revoked), and throws
 * `TransientAuthError` when every attempt was transient. An attempt that
 * THROWS is treated as transient (it did not answer "dead"). Plug the result
 * straight into `createApiClient({ onTokenExpired })`.
 */
export async function refreshWithBackoff(
  attempt: () => Promise<RefreshAttempt>,
  options: RefreshWithBackoffOptions = {},
): Promise<string | null> {
  const delays = options.delaysMs ?? [500, 1500, 4000];
  const sleep = options.sleep ?? defaultSleep;
  let lastReason = 'unknown';
  for (let i = 0; i <= delays.length; i++) {
    let outcome: RefreshAttempt;
    try {
      outcome = await attempt();
    } catch (err) {
      outcome = { kind: 'transient', reason: err instanceof Error ? err.message : String(err) };
    }
    if (outcome.kind === 'token') return outcome.token;
    if (outcome.kind === 'dead') return null;
    lastReason = outcome.reason;
    if (i < delays.length) await sleep(delays[i]);
  }
  throw new TransientAuthError(
    `Nao foi possivel renovar a sessao agora (${lastReason}). A sessao foi mantida.`,
  );
}

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

export function createApiClient(options: CreateApiClientOptions): ApiClient {
  const { getBaseUrl, getAuthToken, onTokenExpired, onUnauthenticated, onMfaVerified, onOrgSemLicenca } = options;

  async function buildHeaders(token?: string | null): Promise<Record<string, string>> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'X-Noctus-Client': detectNoctusClientHeader(),
    };
    const t = token ?? await getAuthToken();
    if (t) {
      headers['Authorization'] = `Bearer ${t}`;
    }
    // Org-picker intent pin: tells the server which org this SPA believes it
    // is in, so a selection changed elsewhere (another tab) 409s instead of
    // silently acting on a different org.
    const pin = getOrgPin();
    if (pin) headers[ORG_PIN_HEADER] = pin;
    return headers;
  }

  async function handleResponse<T>(response: Response): Promise<T> {
    if (!response.ok) {
      const data = await response.json().catch(() => null);
      const message = data
        ? extractErrorMessage(data, response.status)
        : `Erro HTTP ${response.status}`;
      const retryAfterSeconds = parseRetryAfterSeconds(response.headers.get('retry-after'));
      throw new ApiError(response.status, message, data ?? undefined, retryAfterSeconds);
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
   * → signal `onUnauthenticated` — UNLESS the refresh threw (unanswered,
   * transient): then the session is kept. Otherwise the product bounces to login instead of
   * stranding the user on a shell that 401s every call. The 401 is still returned
   * (and thrown by `handleResponse`), but the redirect will already be in flight.
   */
  // Single-flight: concurrent 401s share one refresh.
  let inflightRefresh: Promise<string | null> | null = null;
  function refreshOnce(): Promise<string | null> {
    if (!inflightRefresh) {
      inflightRefresh = onTokenExpired!().finally(() => { inflightRefresh = null; });
    }
    return inflightRefresh;
  }

  async function fetchWithAuthRetry(url: string, init: RequestInit): Promise<Response> {
    const response = await safeFetch(url, init);
    if (response.status !== 401) return response;

    if (onTokenExpired) {
      let freshToken: string | null;
      try {
        freshToken = await refreshOnce();
      } catch (err) {
        // The refresh did not get an authoritative answer (deploy window,
        // network blip). The session is NOT known to be dead — keep it, and
        // let the caller see this request's 401 instead of logging out.
        // eslint-disable-next-line no-console
        console.warn('[api] session refresh unanswered; keeping the session:', err);
        return response;
      }
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

  /** `mfa_required` from a 403 body (nested or flat shape) → `enrolled` flag. */
  async function readMfaRequired(response: Response): Promise<{ enrolled: boolean | null } | null> {
    if (response.status !== 403) return null;
    const data = await response.clone().json().catch(() => null);
    // Flat `{code, enrolled}` (contract), nested `{error:{...}}`, or FastAPI `{detail:{...}}`.
    const body = data?.error ?? (data?.detail && typeof data.detail === 'object' ? data.detail : data);
    if (body?.code !== 'mfa_required') return null;
    const enrolled = body.enrolled;
    return { enrolled: typeof enrolled === 'boolean' ? enrolled : null };
  }

  // License gate: any 403 `org_sem_licenca` → /sem-acesso (the response still
  // propagates so the caller's promise rejects normally).
  async function checkLicenseRefusal(response: Response): Promise<void> {
    if (response.status !== 403) return;
    const data = await response.clone().json().catch(() => null);
    if (isOrgSemLicencaBody(data)) (onOrgSemLicenca ?? redirectToSemAcesso)();
  }

  // Org-picker: a 409 `org_selection_changed` means the pin is stale. Drop it
  // (so nothing re-sends it) and let the registered handler refetch access +
  // reopen the picker. The response still propagates to the caller.
  async function checkOrgSelectionRefusal(response: Response): Promise<void> {
    if (response.status !== 409) return;
    const data = await response.clone().json().catch(() => null);
    if (isOrgSelectionChangedBody(data)) notifyOrgSelectionChanged();
  }

  // The MFA interceptor wraps the auth-retrying fetch. `raw` (no interceptor)
  // is what the dialog itself talks through — a 403 there must never reopen it.
  let rawClient: ApiClient;
  async function fetchWithMfa(url: string, init: RequestInit): Promise<Response> {
    const response = await fetchWithAuthRetry(url, init);
    await checkLicenseRefusal(response);
    await checkOrgSelectionRefusal(response);
    const required = await readMfaRequired(response);
    if (!required) return response;
    const verified = await mfaChallenge.request({
      enrolled: required.enrolled,
      api: rawClient,
      onVerified: async (result) => {
        await onMfaVerified?.(result);
      },
    });
    if (!verified) return response; // cancelled → caller throws the original 403
    const token = await getAuthToken();
    const headers = { ...(init.headers as Record<string, string>) };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    return fetchWithAuthRetry(url, { ...init, headers });
  }

  function buildClient(fetcher: (url: string, init: RequestInit) => Promise<Response>): ApiClient {
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
      const response = await fetcher(url.toString(), { headers });
      return handleResponse<T>(response);
    },

    async post<T = any>(path: string, body?: unknown): Promise<T> {
      const headers = await buildHeaders();
      const base = getBaseUrl();
      const response = await fetcher(`${base}${path}`, {
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
      const response = await fetcher(`${base}${path}`, {
        method: 'POST',
        headers,
        body: form,
      });
      return handleResponse<T>(response);
    },

    async patch<T = any>(path: string, body?: unknown): Promise<T> {
      const headers = await buildHeaders();
      const base = getBaseUrl();
      const response = await fetcher(`${base}${path}`, {
        method: 'PATCH',
        headers,
        body: body ? JSON.stringify(body) : undefined,
      });
      return handleResponse<T>(response);
    },

    async put<T = any>(path: string, body?: unknown): Promise<T> {
      const headers = await buildHeaders();
      const base = getBaseUrl();
      const response = await fetcher(`${base}${path}`, {
        method: 'PUT',
        headers,
        body: body ? JSON.stringify(body) : undefined,
      });
      return handleResponse<T>(response);
    },

    async delete<T = any>(path: string, body?: unknown): Promise<T> {
      const headers = await buildHeaders();
      const base = getBaseUrl();
      const response = await fetcher(`${base}${path}`, {
        method: 'DELETE',
        headers,
        body: body ? JSON.stringify(body) : undefined,
      });
      return handleResponse<T>(response);
    },

    async download(path: string): Promise<Blob> {
      const headers = await buildHeaders();
      delete headers['Content-Type']; // GET has no body — no reason to declare one
      const base = getBaseUrl();
      const response = await fetcher(`${base}${path}`, { headers });
      if (!response.ok) {
        const data = await response.json().catch(() => null);
        const message = data
          ? extractErrorMessage(data, response.status)
          : `Erro HTTP ${response.status}`;
        const retryAfterSeconds = parseRetryAfterSeconds(response.headers.get('retry-after'));
        throw new ApiError(response.status, message, data ?? undefined, retryAfterSeconds);
      }
      return response.blob();
    },
  };
  }

  rawClient = buildClient(fetchWithAuthRetry);
  return buildClient(fetchWithMfa);
}
