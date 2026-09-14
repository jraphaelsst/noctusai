/**
 * Error → PT-BR message mapping for the Agentes UI (contract §E.2, §E.3,
 * `projects/julia-agents-academia-CONTRACT.md`).
 *
 * Every error reaches this client as the flat `{detail, code}` shape (§0).
 * The seed `ApiClient` (`@noctusai/lib` → `api.ts`) reads `data.detail` in
 * `extractErrorMessage` and throws `ApiError(status, detail, data)` — the
 * backend's own PT-BR text survives to `err.message` (prefixed with
 * `[<status>] `), and the raw `code` now survives too, via `err.code`
 * (seed/lib/frontend/src/api.ts: `ApiError.code` reads the flat `code`
 * field, in addition to the nested `{error: {code}}` shape other backends
 * use).
 *
 * This module matches on `err.code` (sourced from the router code,
 * `products/agents/backend/app/routers/*.py`, plus the seed's
 * `require_scopes` dependency) for the handful of codes that need UI copy
 * DIFFERENT from — or absent from — the backend's own `detail` text:
 *   - the task-specified overrides (`turn_in_progress`, `agent_off`,
 *     `upstream_failed`, `not_configured`)
 *   - `role_missing` / `user_required`, which `require_scopes`
 *     (`noctusai_lib.api.auth.session.scopes`) raises with an ENGLISH
 *     `detail` ("Insufficient role" / "Restricted to human users") — never
 *     shown to a user.
 * Every other code (`not_found`, `already_decided`, `orphaned`,
 * `not_allowed`, `invalid_field`, …) already carries good PT-BR text in the
 * backend's own `detail`, so it passes through unchanged — matching to a
 * TEXT table would only re-couple this module to backend copy, the gap this
 * slice closes (contract slice `seed-apierror-flat-code`).
 */
import { ApiError } from "@noctusai/lib";

/** Overrides keyed on `err.code` — only for codes needing copy the backend's
 * own `detail` doesn't already carry (task-specified UX text, or the seed's
 * `require_scopes` English fallbacks). */
const CODE_MESSAGES: Record<string, string> = {
  turn_in_progress: "Julia ainda está respondendo a mensagem anterior.",
  agent_off: "Julia está desligada — um administrador pode ligá-la em Agentes.",
  upstream_failed: "Não foi possível falar com o social-wiring.",
  not_configured: "Configure a conexão do One Chat.",
  // `require_scopes` (seed) raises these with an English `detail` —
  // `restrict="user_only"` means `user_required` is effectively dead from
  // this browser UI (every caller here is an SSO user), but is mapped
  // defensively rather than left to leak English.
  role_missing: "Sem permissão para esta ação.",
  user_required: "Sem permissão para esta ação.",
};

/** Mirrors the contract §B.0-shaped status taxonomy, keyed by HTTP status —
 * the safety net for a body that isn't contract-shaped at all (no `code`,
 * e.g. a bodiless transport-level failure, or slowapi's 429 when it hasn't
 * sent a usable message). */
const STATUS_FALLBACK: Record<number, string> = {
  401: "Sessão expirada — entre novamente.",
  403: "Sem permissão para esta ação.",
  404: "Não encontrado.",
  409: "Conflito ao salvar — verifique e tente novamente.",
  422: "Dados inválidos — revise os campos destacados.",
  429: "Muitas mensagens em pouco tempo — aguarde um instante e tente novamente.",
};

const GENERIC_FALLBACK = "Ocorreu um erro. Tente novamente.";

/** Strips the seed `ApiError`'s `[<status>] ` message prefix, if present. */
function stripStatusPrefix(message: string): string {
  return message.replace(/^\[\d+\]\s*/, "");
}

/**
 * Resolve a human PT-BR message for any error thrown by an `api.*` call.
 * Use in mutation `onError` handlers, `ChatWindow` adapter rejections, and
 * query `error` branches.
 */
export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.code && CODE_MESSAGES[err.code]) return CODE_MESSAGES[err.code];
    const clean = stripStatusPrefix(err.message);
    // A clean, backend-sent detail always wins — it is the contract's own
    // PT-BR text. Only fall back when the client-side generic placeholder
    // ("Erro HTTP 404") leaked through (no JSON body, or a body without
    // `detail` — e.g. slowapi's own 429 body, which is not contract-shaped).
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
