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

/** pt-BR labels for the field names the Community forms submit. Unknown
 * fields fall back to the raw name — still readable, never English prose. */
const FIELD_LABELS: Record<string, string> = {
  nome: "Nome",
  email: "E-mail",
  telefone: "Telefone",
  senha: "Senha",
  cpf: "CPF",
  cpf_cnpj: "CPF/CNPJ",
  origem: "Origem",
  status: "Status",
  plano_id: "Plano",
  tags: "Tags",
  observacoes: "Observações",
  descricao: "Descrição",
  titulo: "Título",
  preco_centavos: "Preço",
};

interface ValidationItem {
  loc?: unknown;
  type?: unknown;
  ctx?: Record<string, unknown>;
}

function validationMessage(item: ValidationItem): string {
  const loc = Array.isArray(item.loc) ? item.loc : [];
  const field = [...loc].reverse().find((p) => typeof p === "string" && p !== "body");
  const label = typeof field === "string" ? (FIELD_LABELS[field] ?? field) : "Campo";
  const type = typeof item.type === "string" ? item.type : "";
  const ctx = item.ctx ?? {};
  if (type === "missing") return `${label}: campo obrigatório.`;
  if (type === "string_pattern_mismatch" || type === "value_error") return `${label}: formato inválido.`;
  if (type === "string_too_short") return `${label}: mínimo de ${String(ctx.min_length ?? "?")} caracteres.`;
  if (type === "string_too_long") return `${label}: máximo de ${String(ctx.max_length ?? "?")} caracteres.`;
  if (type.endsWith("_type") || type.endsWith("_parsing")) return `${label}: valor inválido.`;
  return `${label}: valor inválido.`;
}

/**
 * FastAPI/Pydantic 422 bodies carry `detail: [{loc, msg, type}]` with English
 * `msg` text. Map each entry to a pt-BR field message so no form leaks raw
 * Pydantic prose. Returns null when the body is not a validation array.
 */
function validationErrorsMessage(err: ApiError): string | null {
  const detail = (err.body as { detail?: unknown } | undefined)?.detail;
  if (err.status !== 422 || !Array.isArray(detail) || detail.length === 0) return null;
  return detail.map((d) => validationMessage((d ?? {}) as ValidationItem)).join(" ");
}

/**
 * Resolve a human pt-BR message for any error thrown by an `api.*` call.
 * Use in mutation `onError` handlers and query `error` branches.
 */
export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    const validation = validationErrorsMessage(err);
    if (validation) return validation;
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
