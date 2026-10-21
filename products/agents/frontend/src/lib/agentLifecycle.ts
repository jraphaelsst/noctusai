/**
 * Agent lifecycle (create / delete) — error copy. The delete route answers 409 with
 * `{"detail": {"code", "message"}}` (object detail), which the seed ApiError flattens to "Erro HTTP 409"
 * for `err.message`; the server's pt-BR `message` is read from `err.body.detail.message` here.
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
    const det = (err.body as { detail?: unknown } | undefined)?.detail;
    const m = det && typeof det === "object" ? (det as { message?: unknown }).message : undefined;
    if (typeof m === "string" && m) message = m;
  }
  return { code, message, hint: code ? (DELETE_BLOCK_HINTS[code] ?? null) : null };
}
