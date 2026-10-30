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
 *
 * `agente_capacidade` (contract §E.11 "Capacity") is a THIRD shape: the
 * backend's own `detail` is the contract's authoritative PT-BR text, so it
 * is never overridden (no `CODE_MESSAGES` entry) — but a 429 body without a
 * usable `detail` must still resolve to that SAME text, not the generic
 * rate-limit fallback (`STATUS_FALLBACK[429]`), which is slowapi's own
 * `RATE_LIMITED` message and would conflate the two distinct 429 causes.
 * `CODE_FALLBACKS` carries that per-code fallback, checked after the
 * backend's `detail` and before the status table.
 *
 * The `Retry-After` countdown called for in §E.11 does NOT live here — the
 * seed `ApiError` (`seed/lib/frontend/src/api.ts`) now parses it onto
 * `ApiError.retryAfterSeconds`, and `useLegacySendAdapter`
 * (`hooks/useLegacyChat.ts`) reads that field to drive the composer's
 * countdown via `ChatSendResult.retryAfterSeconds`
 * (`@noctusai/lib/design-system`'s `<ChatWindow>`). This module only ever
 * resolves the STATIC PT-BR text; the live "tente novamente em Ns" is a
 * concern of the send adapter + organ, not the message mapper.
 */
import { ApiError } from "@noctusai/lib";

/** Overrides keyed on `err.code` — only for codes needing copy the backend's
 * own `detail` doesn't already carry (task-specified UX text, or the seed's
 * `require_scopes` English fallbacks). */
const CODE_MESSAGES: Record<string, string> = {
  turn_in_progress: "Bia ainda está respondendo a mensagem anterior.",
  agent_off: "Bia está desligada — um administrador pode ligá-la em Agentes.",
  upstream_failed: "Não foi possível falar com o social-wiring.",
  not_configured: "Configure a conexão do One Chat.",
  // `require_scopes` (seed) raises these with an English `detail` —
  // `restrict="user_only"` means `user_required` is effectively dead from
  // this browser UI (every caller here is an SSO user), but is mapped
  // defensively rather than left to leak English.
  role_missing: "Sem permissão para esta ação.",
  user_required: "Sem permissão para esta ação.",
  // Skills library (`skills_biblioteca_router`).
  skill_incompleta: "Preencha a descrição para o modelo e o corpo da skill antes de publicar.",
  version_immutable: "Esta versão já foi publicada e não pode mais ser alterada. Crie um novo rascunho.",
  platform_admin_required: "Restrito a administradores da plataforma NoctusAI.",
};

/** Per-code fallback text, used only when the backend's own `detail` is
 * absent/unusable — never overrides a real `detail` (unlike `CODE_MESSAGES`).
 * Contract §E.11: the backend's `detail` for `agente_capacidade` already IS
 * this exact string; this fallback exists only for the edge case of a
 * 429 body missing `detail`, so it must stay byte-identical to the
 * contract's PT-BR text. */
const CODE_FALLBACKS: Record<string, string> = {
  agente_capacidade:
    "A Bia está atendendo o número máximo de conversas agora. Tente novamente em instantes.",
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

/**
 * This router's errors arrive as `{"detail": {"detail": "<texto>", "code": "<code>"}}` — the seed
 * `extractErrorMessage` cannot read an OBJECT detail and leaks "Erro HTTP 409". Read the inner text.
 */
function nestedDetail(body: unknown): string | null {
  const det = (body as { detail?: unknown } | null | undefined)?.detail;
  if (det && typeof det === "object" && !Array.isArray(det)) {
    const inner = (det as { detail?: unknown }).detail;
    if (typeof inner === "string" && inner.trim()) return inner;
  }
  return null;
}

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
    const nested = nestedDetail(err.body);
    if (nested) return nested;
    // FastAPI validation (`{"detail":[{loc,msg,type}]}`): the seed joins the English pydantic msgs.
    if (err.status === 422 && Array.isArray((err.body as { detail?: unknown } | undefined)?.detail)) {
      return STATUS_FALLBACK[422];
    }
    // A clean, backend-sent detail always wins — it is the contract's own
    // PT-BR text. Only fall back when the client-side generic placeholder
    // ("Erro HTTP 404") leaked through (no JSON body, or a body without
    // `detail` — e.g. slowapi's own 429 body, which is not contract-shaped).
    if (clean && !/^Erro HTTP \d+$/.test(clean)) return clean;
    // A per-code fallback (currently only `agente_capacidade`) beats the
    // generic status table, so a capacity 429 without a usable `detail`
    // never gets mistaken for slowapi's rate-limit 429.
    if (err.code && CODE_FALLBACKS[err.code]) return CODE_FALLBACKS[err.code];
    if (err.status !== null && STATUS_FALLBACK[err.status]) {
      return STATUS_FALLBACK[err.status];
    }
    return clean || GENERIC_FALLBACK;
  }
  if (err instanceof Error) return err.message;
  return GENERIC_FALLBACK;
}

export { ApiError };
