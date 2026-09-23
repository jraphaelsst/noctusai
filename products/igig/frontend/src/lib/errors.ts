/**
 * The server's own refusal text, for toasts and inline errors.
 *
 * The seed `ApiError` message is `[<status>] <message>`; the backend's rule
 * refusals (409/422) carry a pt-BR `detail` the operator can act on
 * ("Gere o PDF antes de enviar", "orçamento bloqueado"…). Showing that text
 * verbatim — without the status prefix — beats any generic "algo deu errado".
 */
import { ApiError } from "@noctusai/lib";

export function describeError(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    const body = err.body as { detail?: unknown; error?: { message?: unknown } } | undefined;
    if (typeof body?.detail === "string" && body.detail) return body.detail;
    if (typeof body?.error?.message === "string" && body.error.message) return body.error.message;
    const semPrefixo = err.message.replace(/^\[\d+\]\s*/, "");
    return semPrefixo || fallback;
  }
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

/** The `code` of a `{detail, code}` / `{error: {code}}` refusal, or null. */
export function errorCode(err: unknown): string | null {
  return err instanceof ApiError ? err.code : null;
}
