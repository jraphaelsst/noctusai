/**
 * API surface for Monica.
 *
 * Re-exports the shared `api` client (and the session-token provider the inbox's SSE stream needs) from the seed
 * boundary so product code imports from `@/lib/api` instead of reaching into `@noctusai/seed/infra` directly.
 * That also makes `vi.mock("@/lib/api", ...)` the single, short test seam for every page and hook.
 */
export { api, getAuthToken } from "@noctusai/seed/infra";
