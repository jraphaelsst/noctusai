/**
 * Error → PT-BR message mapping for the Community UI.
 *
 * community-m1-contract.md guarantees every error reaches the client as
 * FastAPI's default `{"detail": "..."}` shape, in pt-BR, user-facing. The
 * seed `ApiClient` (`@noctusai/lib` → `api.ts`) already reads `data.detail`
 * in `extractErrorMessage` and throws `ApiError(status, detail, data)` — the
 * backend's pt-BR text survives to `err.message` (prefixed with
 * `[<status>] `). This module strips that prefix so a 403 from a
 * `moderador` write attempt (or any other contract error) renders the
 * server's own message verbatim, never a generic placeholder.
 *
 * Mirrors `products/academia-de-reciclagem/frontend/src/lib/errors.ts` —
 * same shape, no `code`-keyed overrides needed here because this contract
 * has none (every status maps straight to the backend's own `detail`).
 */
import { ApiError } from "@noctusai/lib";

const GENERIC_FALLBACK = "Ocorreu um erro. Tente novamente.";

/** Strips the seed `ApiError`'s `[<status>] ` message prefix, if present. */
function stripStatusPrefix(message: string): string {
  return message.replace(/^\[\d+\]\s*/, "");
}

/**
 * Resolve a human pt-BR message for any error thrown by an `api.*` call.
 * Use in mutation `onError` handlers and query `error` branches.
 */
export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    const clean = stripStatusPrefix(err.message);
    // A clean, backend-sent `detail` always wins — it is the contract's own
    // pt-BR text. Only fall back when the client-side generic placeholder
    // ("Erro HTTP 404") leaked through (no JSON body, or a body without
    // `detail`).
    if (clean && !/^Erro HTTP \d+$/.test(clean)) return clean;
    return clean || GENERIC_FALLBACK;
  }
  if (err instanceof Error) return err.message;
  return GENERIC_FALLBACK;
}

export { ApiError };
