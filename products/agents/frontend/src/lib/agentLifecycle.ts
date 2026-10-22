/**
 * Agent lifecycle (create / delete) — error copy. The delete route answers 409 with the flat Studio
 * error body `{code, message, detail}`; `ApiError.code` reads `code`, and the server's pt-BR `message`
 * is read from `err.body.message` here (seed ApiError's own `err.message` is only "Erro HTTP 409").
 */
import { ApiError } from "@noctusai/lib";
import { errorMessage } from "@/lib/errors";

export const DELETE_BLOCK_HINTS: Record<string, string> = {
  publicado: "Despublique a versão ativa antes de excluir.",
  tem_instancias: "Remova as instâncias das organizações antes de excluir.",
  tem_conversas: "O agente tem conversas registradas e não pode ser excluído.",
  tem_canal: "Desconecte o canal do agente antes de excluir.",
  ativo: "Desligue o agente antes de excluir.",
};

/** FastAPI's default 422 body: `{detail: [{loc, msg, type}]}` -> "campo: mensagem; ..." (no flat `message`). */
function validationMessage(detail: unknown[]): string | null {
  const parts = detail
    .map((d) => {
      const e = d as { loc?: unknown; msg?: unknown };
      if (typeof e?.msg !== "string") return null;
      const loc = Array.isArray(e.loc) ? e.loc.filter((x) => x !== "body").join(".") : "";
      return loc ? `${loc}: ${e.msg}` : e.msg;
    })
    .filter((x): x is string => !!x);
  return parts.length ? parts.join("; ") : null;
}

export interface LifecycleError {
  code: string | null;
  message: string;
  hint: string | null;
}

export function lifecycleError(err: unknown): LifecycleError {
  const code = err instanceof ApiError ? err.code : null;
  let message = errorMessage(err);
  if (err instanceof ApiError) {
    const body = err.body as { message?: unknown; detail?: unknown } | undefined;
    if (typeof body?.message === "string" && body.message) message = body.message;
    else if (Array.isArray(body?.detail)) message = validationMessage(body.detail) ?? message;
  }
  return { code, message, hint: code ? (DELETE_BLOCK_HINTS[code] ?? null) : null };
}
