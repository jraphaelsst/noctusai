/**
 * Resolve the backend API base URL — noc house single-container model.
 *
 * social-wiring runs as ONE container: uvicorn serves the built SPA
 * AND the API on the same port via the seed `serve_spa` seam. So the
 * default is **same-origin** — `/api/*` already routes to the backend
 * in-process, no CORS, one URL for direct / tunnel / proxy access.
 *
 * Two modes only (the originating workspace's 2-container proxy mode
 * is gone — superseded by `serve_spa` per the divergent-arch → house
 * refactor rule):
 *
 * 1. EXPLICIT — `VITE_BACKEND_API_URL` set at build time → use it.
 *    Reserved for staging that points at a non-co-located backend.
 *    NOTE: do NOT bake this in the product image — it is intentionally
 *    runtime-detected so one artifact serves direct/tunnel/proxy.
 *
 * 2. SAME-ORIGIN (default) — empty string → every `fetch()` is
 *    same-origin. Works for the single container, the profile-gated
 *    `<slug>-tunnel`, and any reverse proxy fronting it.
 *
 * Local-dev fallback: when the page is served directly off the Vite
 * dev port (8160) without the single-container backend co-located,
 * fall back to the conventional product backend address (8011) so a
 * bare `vite` dev server still talks to a separately-run backend.
 *
 * The decision happens AT RUNTIME (reads `window.location`) so a
 * single build artifact works for every access mode — no rebuild
 * when switching between local-dev, single-container, and tunnel.
 */
const FRONTEND_DEV_PORT = "8160";
const BACKEND_DIRECT_URL = "http://localhost:8011";

export function apiBase(): string {
  const configured = import.meta.env.VITE_BACKEND_API_URL;
  if (typeof configured === "string" && configured.length > 0) {
    return configured;
  }
  if (typeof window === "undefined") {
    return BACKEND_DIRECT_URL;
  }
  // Bare Vite dev port → talk to a separately-run backend. Anything
  // else (single container, tunnel hostname, prod hostname) →
  // same-origin (the seed serve_spa serves SPA + API on one port).
  return window.location.port === FRONTEND_DEV_PORT ? BACKEND_DIRECT_URL : "";
}

export function apiUrl(path: string): string {
  const base = apiBase();
  if (!base) return path;
  return `${base.replace(/\/$/, "")}${path.startsWith("/") ? path : `/${path}`}`;
}
