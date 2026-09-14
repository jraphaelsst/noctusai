/**
 * Error → PT-BR message mapping for the academia-de-reciclagem UI.
 *
 * The contract (`projects/julia-agents-academia-CONTRACT.md` §0, §B.0)
 * guarantees every error reaches the client as `{detail, code}`, with
 * `detail` already the PT-BR message named in the §B.0 status taxonomy
 * table. The seed `ApiClient` (`@noctusai/lib` → `api.ts`) already reads
 * `data.detail` in `extractErrorMessage` and throws `ApiError(status,
 * detail)` — the backend's PT-BR text survives all the way to `err.message`,
 * just prefixed with `[<status>] `.
 *
 * `ApiError` does NOT retain the raw `code` field (a seed-level gap: fixing
 * it means changing `@noctusai/lib`'s `ApiError`/`extractErrorMessage`,
 * out of scope for this product slice — flagged in the engineer report as
 * `scoped-improvement:`). So this module's map is keyed on HTTP `status`
 * (available via `err.status`), which is enough to reproduce every row of
 * the contract's status taxonomy table EXCEPT the two 403 sub-codes
 * (`scope_missing` vs `assertion_invalid`) and the two 409 sub-codes
 * (`assertion_used` vs `conflict`) — those already arrive correctly in
 * `err.message` because the backend's `detail` text differs per code even
 * though the status is shared, so `errorMessage()` prefers the live
 * `err.message` and only falls back to a generic per-status string when the
 * backend didn't send one (e.g. a transport-level failure, `status === null`).
 */
import { ApiError } from "@noctusai/lib";

/** Mirrors the contract §B.0 "Message for the user" column, keyed by status. */
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
