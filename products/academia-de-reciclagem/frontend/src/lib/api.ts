/**
 * API surface for Academia de Reciclagem.
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
import { api } from "@noctusai/seed/infra";

export { api };

/**
 * `POST /api/public/interessados` — no auth (`projects/interessados-
 * CONTRACT.md`). The fleet's first unauthenticated write route: the seed
 * `ApiClient` sends it token-less (`getAuthToken()` resolves `null` for a
 * signed-out visitor and the request still goes out — see
 * `seed/lib/frontend/src/api.ts` `CreateApiClientOptions.getAuthToken`), so
 * no seed change was needed to call this from a public page.
 *
 * A typed wrapper (rather than an inline `api.post` in the popup component,
 * per this file's TODO) because the wire shape is awkward: `consentimento`
 * must be the literal `true`, and the caller has no reason to see that shape
 * more than once.
 */
export interface CreateInteressadoInput {
  nome: string;
  whatsapp: string;
  email: string;
  /** The act of opting in — always `true` on submit (§ contract). */
  consentimento: true;
  /** Public page path the popup was submitted from (`/`, `/como-funciona`, `/a-carta`). */
  origem?: string;
}

export interface CreateInteressadoResult {
  ok: true;
}

export function createInteressado(input: CreateInteressadoInput): Promise<CreateInteressadoResult> {
  return api.post<CreateInteressadoResult>("/api/public/interessados", input);
}
