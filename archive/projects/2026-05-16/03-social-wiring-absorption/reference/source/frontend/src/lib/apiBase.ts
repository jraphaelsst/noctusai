/**
 * Resolve the backend API base URL.
 *
 * Three modes:
 *
 * 1. EXPLICIT — `VITE_BACKEND_API_URL` is set at build time. Use it.
 *    Useful for staging deploys that want to point at a non-co-located
 *    backend.
 *
 * 2. PROXIED — the page itself is served behind the reverse-proxy
 *    (`proxy` service on port 8090, or the public Cloudflare tunnel
 *    that fronts it). The proxy already routes `/api/*` to the
 *    backend, so we return an EMPTY string and every `fetch()`
 *    becomes same-origin. No CORS preflight, one URL for everything.
 *
 * 3. DIRECT-FRONTEND — page served directly off the frontend
 *    container at `localhost:8150` without the proxy. Fall back to
 *    the conventional backend address so local dev keeps working
 *    even when someone bypasses the proxy.
 *
 * The decision happens AT RUNTIME (reads `window.location`) so a
 * single build artifact works for all three modes — no rebuild
 * required when switching between local-dev, proxy, and tunnel
 * access.
 */
const FRONTEND_DIRECT_PORT = "8150";
const BACKEND_DIRECT_URL = "http://localhost:8010";

export function apiBase(): string {
  const configured = import.meta.env.VITE_BACKEND_API_URL;
  if (typeof configured === "string" && configured.length > 0) {
    return configured;
  }
  if (typeof window === "undefined") {
    return BACKEND_DIRECT_URL;
  }
  // Direct frontend port → fall back to localhost backend. Anything
  // else (proxy:8090, tunnel hostname, prod hostname) → same-origin.
  return window.location.port === FRONTEND_DIRECT_PORT ? BACKEND_DIRECT_URL : "";
}

export function apiUrl(path: string): string {
  const base = apiBase();
  if (!base) return path;
  return `${base.replace(/\/$/, "")}${path.startsWith("/") ? path : `/${path}`}`;
}
