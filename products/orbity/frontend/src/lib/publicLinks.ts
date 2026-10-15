/**
 * Public (no-auth) link builders for Orbity.
 *
 * The SPA mounts the public pages at `/aprovar/:token` and `/relatorio/:token`
 * (see App.tsx `publicRoutes`). `/api/...` is the BACKEND surface — a link
 * built against it hands the client a JSON/404 page instead of the UI, so the
 * paths live here, in one place, next to a test.
 */

function origin(): string {
  return typeof window !== "undefined" ? window.location.origin : "";
}

export function approvalPublicPath(token: string): string {
  return `/aprovar/${encodeURIComponent(token)}`;
}

export function reportPublicPath(token: string): string {
  return `/relatorio/${encodeURIComponent(token)}`;
}

export function approvalPublicUrl(token: string, base: string = origin()): string {
  return `${base}${approvalPublicPath(token)}`;
}

export function reportPublicUrl(token: string, base: string = origin()): string {
  return `${base}${reportPublicPath(token)}`;
}
