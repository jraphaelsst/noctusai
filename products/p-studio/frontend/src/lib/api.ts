import { supabase } from "./supabase";

// House single-container model: uvicorn serves the built SPA + API on the
// SAME origin (via the seed `serve_spa` seam), so the default is same-origin
// (empty string → relative fetch). `vite.config.factory.ts` `define`-rewrites
// `VITE_BACKEND_API_URL` at build time to `window.location.origin` when
// `VITE_SAME_ORIGIN=1` (every product Dockerfile sets it), or to the
// registry-resolved `http://localhost:<backendPort>` for bare two-port dev.
// Mirrors `seed/framework/frontend/src/infra.tsx`'s `createProductInfra` —
// no hardcoded localhost fallback (a fallback surviving into the prod
// bundle previously routed every product's FE at core's port; see
// `KB § PATTERNS/frontend/core-url-routing.md`).
const BASE = import.meta.env.VITE_BACKEND_API_URL ?? "";

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const {
    data: { session },
  } = await supabase.auth.getSession();

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(session ? { Authorization: `Bearer ${session.access_token}` } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = (data as any)?.detail;
    const message =
      typeof detail === "string" ? detail : detail ? JSON.stringify(detail) : `Erro ${res.status}`;
    throw new Error(message);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),
};

/** Monta `?a=1&b=2` ignorando chaves vazias. */
export function qs(params?: Record<string, string | number | undefined | null>): string {
  if (!params) return "";
  const entries = Object.entries(params).filter(
    ([, v]) => v !== undefined && v !== null && v !== ""
  );
  return entries.length ? `?${new URLSearchParams(entries.map(([k, v]) => [k, String(v)]))}` : "";
}
