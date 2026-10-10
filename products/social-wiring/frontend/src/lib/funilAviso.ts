/**
 * Surfaces a refused funnel move (CONTRACT §6: "the caller surfaces `motivo`").
 *
 * The create endpoints (roteiro, proposta) answer `funil: {moveu, motivo}`.
 * `moveu:false` is benign when the card is already where the event wants it
 * (`ja_na_etapa`, `ja_adiante`) or the event is a no-op; anything else is a
 * real refusal (e.g. a stage gate naming the missing field) the operator must
 * see — a bare "criado" toast would hide that the card did not move.
 */
import { toast } from "sonner";

export interface FunilResultado {
  moveu: boolean;
  de?: string | null;
  para?: string | null;
  motivo?: string | null;
}

const MOTIVOS_BENIGNOS = new Set(["ja_na_etapa", "ja_adiante", "noop"]);

export function funilRecusado(funil: FunilResultado | null | undefined): string | null {
  if (!funil || funil.moveu !== false) return null;
  const motivo = funil.motivo?.trim();
  if (!motivo || MOTIVOS_BENIGNOS.has(motivo)) return null;
  return motivo;
}

/** Warns with the refusal reason; returns whether one was shown. */
export function avisarFunilRecusado(funil: FunilResultado | null | undefined): boolean {
  const motivo = funilRecusado(funil);
  if (!motivo) return false;
  toast.warning("O card não avançou de etapa", { description: motivo });
  return true;
}
