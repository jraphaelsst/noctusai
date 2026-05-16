/**
 * API surface for Social Wiring.
 *
 * Re-exports the shared `api` client from the seed boundary so product
 * code imports from `@/lib/api` instead of reaching into
 * `@noctusai/seed/infra` directly. Two reasons this layer exists:
 *
 *   1. Test seam — `vi.mock("@/lib/api", ...)` is shorter and more
 *      stable than mocking the seed boundary in every hook test.
 *   2. Domain-call wrappers live here when the wire shape is awkward
 *      (e.g., translating `{items, next_cursor}` into a paginator).
 *
 * Mirrors the 5-product convention (core, dev-team, ERP, PF, therapy).
 *
 * The ported CMS hooks (useDashboard / useVideos / useSettings /
 * useWhatsApp*) call `api` from `@noctusai/seed/infra` directly today
 * (live-validated shape). Streaming/multipart paths (useChat,
 * useUpload) use raw `fetch` via `@/lib/apiBase` on purpose — the
 * seed `api` client is JSON-only. Typed per-domain wrappers can land
 * here when a wire shape gets awkward (e.g. cursor pagination).
 */
export { api } from "@noctusai/seed/infra";
