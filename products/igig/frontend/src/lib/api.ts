/**
 * API surface for IgIg.
 *
 * Re-exports the shared `api` client from the seed boundary so product
 * code imports from `@/lib/api` instead of reaching into
 * `@noctusai/seed/infra` directly. Two reasons this layer exists:
 *
 *   1. Test seam — `vi.mock("@/lib/api", ...)` is shorter and more
 *      stable than mocking the seed boundary in every hook test.
 *   2. Domain-call wrappers live here when the wire shape is awkward.
 *
 * `unwrapData` — the CRM endpoints (funnel, orçamentos, produtos, e-mail)
 * answer the seed `{data: …}` envelope (wave-2 contract § Conventions); the
 * older módulo routers answer bare payloads. The seed client returns the body
 * as-is, so every CRM hook unwraps through this one helper instead of
 * sprinkling `.data` reads (and silently getting `undefined` when a router
 * answers bare). Hooks call `api.<verb>("/literal/path").then(unwrapData<T>)`
 * — never a path-hiding wrapper — so `noctus.dev.scan_wiring` can still match
 * every call against the backend routes.
 */
export { api } from "@noctusai/seed/infra";

/** `{data: T}` → `T`. A bare payload (no `data` key) is returned unchanged. */
export function unwrapData<T>(body: unknown): T {
  if (body && typeof body === "object" && "data" in (body as Record<string, unknown>)) {
    return (body as { data: T }).data;
  }
  return body as T;
}

/** Drop `undefined` / empty-string entries so they never reach the query string. */
export function cleanParams(params: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ""),
  );
}
