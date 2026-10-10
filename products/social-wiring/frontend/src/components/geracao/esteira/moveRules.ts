/**
 * Esteira move rules — the CLIENT mirror of esteira-contract.md §4.
 *
 * The server is the authority (`mover_post`: 409 `pendencias` / `etapa_invalida`,
 * 422 `motivo_obrigatorio`). This only picks the right dialog BEFORE the
 * request, so the board never sends a move it already knows needs a reason.
 * Keyed on stage ROLE (`papel`) and display ORDER (`direction`), never on
 * labels — stages are user-editable.
 *
 * Forward moves are FREE at any distance (owner decision D3: reels skip stages).
 */
import type { MoveIntentContext, PipelineStage } from "@noctusai/lib/components";

import type { PapelEsteira } from "@/types/esteira";

export const PAPEL_GRAVACAO: PapelEsteira = "gravacao";
export const PAPEL_POSTADO: PapelEsteira = "postado";
export const PAPEL_CANCELADO: PapelEsteira = "cancelado";

/** Role → label shown in the stage editor (§6.1). */
export const ESTEIRA_ROLE_LABELS: Record<PapelEsteira, string> = {
  gravacao: "Início da produção",
  postado: "Publicado",
  cancelado: "Encerrado",
};

export type DecisaoMovimento =
  /** Send as dropped (reorder, or any forward move). */
  | { tipo: "seguir" }
  /** Backward / cancel / reactivate: a reason is required first. */
  | { tipo: "motivo"; titulo: string; descricao: string; placeholder: string; confirmar: string }
  /** Into the `postado` role: ask for the (optional) permalink. */
  | { tipo: "postado" };

type Contexto = Pick<MoveIntentContext<unknown>, "direction"> & {
  fromStage: Pick<PipelineStage, "label" | "papel">;
  toStage: Pick<PipelineStage, "label" | "papel">;
};

export function decidirMovimento(ctx: Contexto): DecisaoMovimento {
  if (ctx.direction === "same") return { tipo: "seguir" };

  if (ctx.toStage.papel === PAPEL_CANCELADO) {
    return {
      tipo: "motivo",
      titulo: "Motivo do bloqueio ou cancelamento",
      descricao: "O motivo fica no histórico do post e aparece no cartão.",
      placeholder: "Por que este post foi bloqueado ou cancelado?",
      confirmar: "Encerrar post",
    };
  }
  if (ctx.direction === "backward") {
    const reativacao = ctx.fromStage.papel === PAPEL_CANCELADO;
    return {
      tipo: "motivo",
      titulo: reativacao ? "Reativar este post?" : "Por que este post está voltando?",
      descricao: reativacao
        ? "O motivo anterior do encerramento é mantido no histórico."
        : "Voltar um post exige um motivo — ele fica no histórico.",
      placeholder: reativacao ? "Por que reativar?" : "Por que voltar?",
      confirmar: reativacao ? "Reativar" : "Devolver",
    };
  }
  if (ctx.toStage.papel === PAPEL_POSTADO) return { tipo: "postado" };
  return { tipo: "seguir" };
}

/** Mirrors the server's `pendencias` 409 so the toast can offer "Abrir post". */
export function ehPendencias(erro: unknown): boolean {
  const b = (erro as { body?: Record<string, any> } | null | undefined)?.body;
  const codigo = b?.code ?? b?.detail?.code ?? b?.error?.code;
  return codigo === "pendencias";
}

export const MENSAGEM_PENDENCIAS =
  "Para entrar em Gravação o post precisa de headline e roteiro concluído.";

/** `instagram.com` links only (the optional permalink asked on `postado`). */
export function permalinkValido(url: string): boolean {
  const v = url.trim();
  if (!v) return true;
  try {
    const u = new URL(v);
    return (
      (u.protocol === "https:" || u.protocol === "http:") &&
      (u.hostname === "instagram.com" || u.hostname.endsWith(".instagram.com"))
    );
  } catch {
    return false;
  }
}
