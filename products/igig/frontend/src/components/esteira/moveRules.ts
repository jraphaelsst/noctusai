/**
 * Esteira move rules — the CLIENT half of roadmap R3.
 *
 * The server is the authority (`app/services/esteira_quadro.py::mover_tarefa`:
 * 409 `etapa_invalida` on a forward skip, 422 `motivo_obrigatorio` on a
 * backward move without a reason). This mirror exists so the board never sends
 * a request it already knows will be refused: a forward skip is cancelled with
 * a toast before any network round-trip, and a backward move asks for the
 * reason FIRST instead of failing and then asking.
 *
 * Keyed on stage ORDER (the board's display order, via `stepDistance`) and
 * stage ROLE (`papel`), never on labels — the stages are user-editable, so a
 * rule that read "Aprovação do cliente" would break on the first rename.
 */
import type { MoveIntentContext, PipelineStage } from "@noctusai/lib/components";

/** The esteira stage the client-approval portal operates on (backend twin: `PAPEL_APROVACAO_CLIENTE`). */
export const PAPEL_APROVACAO_CLIENTE = "aprovacao_cliente";

export const MENSAGEM_UM_PASSO = "Avance uma etapa por vez";

export type DecisaoMovimento =
  /** Refuse locally — the server would 409. `mensagem` is shown as a toast. */
  | { tipo: "cancelar"; mensagem: string }
  /** Send as dropped (reorder in the column, or forward one step). */
  | { tipo: "seguir" }
  /** Backward: a reason is required before the move is sent. */
  | { tipo: "motivo"; titulo: string; refacao: boolean };

type Contexto = Pick<MoveIntentContext<unknown>, "direction" | "stepDistance"> & {
  fromStage: Pick<PipelineStage, "label" | "papel">;
  toStage: Pick<PipelineStage, "label" | "papel">;
};

export function decidirMovimento(ctx: Contexto): DecisaoMovimento {
  if (ctx.direction === "same") return { tipo: "seguir" };
  if (ctx.direction === "forward") {
    return ctx.stepDistance > 1
      ? { tipo: "cancelar", mensagem: MENSAGEM_UM_PASSO }
      : { tipo: "seguir" };
  }
  // Backward, any distance — but never without a reason. Leaving the approval
  // stage backwards IS a refação (the server counts it atomically); the dialog
  // says so, so nobody is surprised by the counter going up.
  const refacao = ctx.fromStage.papel === PAPEL_APROVACAO_CLIENTE;
  return {
    tipo: "motivo",
    refacao,
    titulo: refacao
      ? `Refação — devolver para ${ctx.toStage.label}?`
      : `Devolver para ${ctx.toStage.label}?`,
  };
}
