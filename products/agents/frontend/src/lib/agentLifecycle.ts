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

export interface LifecycleError {
  code: string | null;
  message: string;
  hint: string | null;
}

export function lifecycleError(err: unknown): LifecycleError {
  const code = err instanceof ApiError ? err.code : null;
  let message = errorMessage(err);
  if (err instanceof ApiError) {
    const m = (err.body as { message?: unknown } | undefined)?.message;
    if (typeof m === "string" && m) message = m;
  }
  return { code, message, hint: code ? (DELETE_BLOCK_HINTS[code] ?? null) : null };
}
