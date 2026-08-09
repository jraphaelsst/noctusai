/**
 * API surface for IgIg.
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
 * Mirrors the 4-product convention (core, dev-team, ERP, PF, therapy).
 *
 * TODO(new-product): add typed wrapper functions per domain endpoint
 * (e.g., `listExamples()`, `createExample(payload)`). The hooks in
 * `src/hooks/` then call these wrappers instead of `api.get(url)`
 * directly — keeps URL strings + payload shapes in one place.
 */
export { api } from "@noctusai/seed/infra";
