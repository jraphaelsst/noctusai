/**
 * Error → PT-BR message mapping for the Agentes UI (contract §E.2, §E.3,
 * `projects/julia-agents-academia-CONTRACT.md`).
 *
 * Every error reaches this client as the flat `{detail, code}` shape (§0).
 * The seed `ApiClient` (`@noctusai/lib` → `api.ts`) reads `data.detail`
 * in `extractErrorMessage` and throws `ApiError(status, detail)` — the
 * backend's own PT-BR text survives to `err.message`, prefixed with
 * `[<status>] `.
 *
 * `ApiError` does NOT retain the raw `code` field — a seed-level gap
 * (`seed/lib/frontend/src/api.ts`): fixing it means changing the shared
 * `ApiClient`/`ApiError`, out of scope for this product slice. The
 * `academia-de-reciclagem` UI hit the exact same gap on the same contract
 * (`products/academia-de-reciclagem/frontend/src/lib/errors.ts`) — this is
 * now the SECOND instance (`scoped-improvement:` in the delivery report,
 * DRY N=2 → triage).
 *
 * So this module matches on the raw backend `detail` TEXT (sourced directly
 * from the router code, `products/agents/backend/app/routers/*.py`) rather
 * than on `code`, and overrides it with the task-specified PT-BR copy where
 * one was given. Approval `already_decided` / `orphaned` pass the backend's
 * own text through unchanged — it already matches the contract's intent —
 * and the caller (see `useApprovals.ts` / `useJuliaChat.ts`) refetches after
 * showing it, per contract §E.2.
 */
import { ApiError } from "@noctusai/lib";

/** Mirrors the contract §B.0-shaped status taxonomy, keyed by HTTP status. */
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
 * Overrides keyed on the EXACT backend `detail` string, for the codes the
 * task spec gives different UI copy than the backend's own PT-BR text.
 * Backend source: `app/routers/conversations_router.py`,
 * `app/routers/agents_router.py`.
 */
const DETAIL_OVERRIDES: Record<string, string> = {
  "Já existe um turno em andamento.": // 409 turn_in_progress
    "Julia ainda está respondendo a mensagem anterior.",
  "O agente Julia está desligado.": // 409 agent_off
    "Julia está desligada — um administrador pode ligá-la em Agentes.",
  "Falha ao comunicar com o social-wiring.": // 502 upstream_failed
    "Não foi possível falar com o social-wiring.",
  "One Chat ainda não configurado (nenhuma conexão vinculada).": // 409 not_configured
    "Configure a conexão do One Chat.",
};

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
    const clean = stripStatusPrefix(err.message);
    if (clean && DETAIL_OVERRIDES[clean]) return DETAIL_OVERRIDES[clean];
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
