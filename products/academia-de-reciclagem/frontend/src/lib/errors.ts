/**
 * Error → PT-BR message mapping for the academia-de-reciclagem UI.
 *
 * The contract (`projects/julia-agents-academia-CONTRACT.md` §0, §B.0)
 * guarantees every error reaches the client as `{detail, code}`. The seed
 * `ApiClient` (`@noctusai/lib` → `api.ts`) reads `data.detail` in
 * `extractErrorMessage` and throws `ApiError(status, detail, data)` — the
 * backend's PT-BR text survives to `err.message` (prefixed with
 * `[<status>] `), and the raw `code` now survives too, via `err.code`
 * (`seed/lib/frontend/src/api.ts`: `ApiError.code` reads the flat `code`
 * field, in addition to the nested `{error: {code}}` shape other backends
 * use).
 *
 * This module matches on `err.code`, keyed with the EXACT wording from the
 * contract's §B.0 status-taxonomy table — pinning to the contract rather
 * than to whatever text a given router happens to send, which is what
 * decouples the two 403 sub-codes (`scope_missing` vs `assertion_invalid`)
 * and the two 409 sub-codes (`assertion_used` vs `conflict`) that share an
 * HTTP status and previously could not be told apart from `err.status`
 * alone. `role_missing` (the SSO-user analogue of `scope_missing` — a
 * member without the route's WRITE/ADMIN role) gets the same copy: both
 * mean "this caller may act, but lacks the specific permission," and
 * `require_scopes` (`noctusai_lib.api.auth.session.scopes`) raises
 * `role_missing` with an ENGLISH `detail` ("Insufficient role") that must
 * never reach a user.
 *
 * Every other code (`not_found`, `conflict`, `invalid`, `approver_not_
 * allowed`, `product_forbidden`, `bundle_too_large`, `secret_detected`,
 * `bundle_invalid`, …) already carries good, often per-instance, PT-BR text
 * in the backend's own `detail` (e.g. `conflict`'s message is "Specific
 * message per endpoint" by contract design), so it passes through
 * unchanged — mapping it to a fixed string would throw away information
 * the backend already computed.
 */
import { ApiError } from "@noctusai/lib";

/** Overrides keyed on `err.code`, worded EXACTLY per the contract §B.0
 * status-taxonomy table — the fix for the two 403 / two 409 sub-code pairs
 * this module could not previously distinguish, plus `role_missing`'s
 * English backend text. */
const CODE_MESSAGES: Record<string, string> = {
  scope_missing: "Sem permissão para esta ação.",
  role_missing: "Sem permissão para esta ação.",
  assertion_invalid: "Aprovação inválida — peça de novo.",
  assertion_used: "Esta aprovação já foi usada.",
};

/** Mirrors the contract §B.0 "Message for the user" column, keyed by
 * status — the safety net for a body that isn't contract-shaped at all
 * (no `code`, e.g. a transport-level failure). */
const STATUS_FALLBACK: Record<number, string> = {
  401: "Sessão expirada — entre novamente.",
  403: "Sem permissão para esta ação.",
  404: "Não encontrado.",
  409: "Conflito ao salvar — verifique e tente novamente.",
  422: "Dados inválidos — revise os campos destacados.",
};

const GENERIC_FALLBACK = "Ocorreu um erro. Tente novamente.";

/** Strips the seed `ApiError`'s `[<status>] ` message prefix, if present. */
function stripStatusPrefix(message: string): string {
  return message.replace(/^\[\d+\]\s*/, "");
}

/**
 * Resolve a human PT-BR message for any error thrown by an `api.*` call.
 * Use in mutation `onError` handlers and query `error` branches.
 */
export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.code && CODE_MESSAGES[err.code]) return CODE_MESSAGES[err.code];
    const clean = stripStatusPrefix(err.message);
    // A clean, backend-sent detail always wins — it is the contract's own
    // PT-BR text. Only fall back when the client-side generic placeholder
    // ("Erro HTTP 404") leaked through (no JSON body, or a body without
    // `detail`).
    if (clean && !/^Erro HTTP \d+$/.test(clean)) return clean;
    if (err.status !== null && STATUS_FALLBACK[err.status]) {
      return STATUS_FALLBACK[err.status];
    }
    return clean || GENERIC_FALLBACK;
  }
  if (err instanceof Error) return err.message;
  return GENERIC_FALLBACK;
}

export { ApiError };
