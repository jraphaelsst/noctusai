/**
 * Parcela ORDER + human LABEL — shared by every schedule that lists parcelas
 * (the negociação's `ParcelasSection`, the aditivo's restated schedule, the
 * termos' posse-marco picker), so the three never disagree on what "Parcela
 * 03" is or how to move one.
 *
 * 🔴 A parcela is never shown to a person by its id (owner, 2026-10-03: a
 * parcela with no `evento` printed its raw UUID in the posse-marco picker).
 */
import { exibirData, exibirMoeda } from "@/lib/moedaDecimal";
import { PARCELA_TIPO_LABELS, type ParcelaTipo } from "@/types/negociacaoEstruturada";

/** "Parcela 03" — two digits, like the generated contract. `posicao` is 1-based. */
export function numeroParcela(posicao: number): string {
  return `Parcela ${String(posicao).padStart(2, "0")}`;
}

/** The fields a label needs — a `NegociacaoParcela` and an aditivo parcela fit. */
export interface ParcelaRotulavel {
  tipo: ParcelaTipo;
  valor: string | null;
  evento: string | null;
  vencimento: string | null;
}

/** "Parcela NN — <tipo> — <evento | vencimento> — R$ x" (the moment only
 *  when there is one; "valor a definir" for an extracted parcela awaiting
 *  its value, migration 171). Never an id. */
export function rotuloParcela(p: ParcelaRotulavel, posicao: number): string {
  const momento = p.evento?.trim() || exibirData(p.vencimento);
  return [
    numeroParcela(posicao),
    PARCELA_TIPO_LABELS[p.tipo] ?? p.tipo,
    momento,
    p.valor == null || p.valor.trim() === "" ? "valor a definir" : exibirMoeda(p.valor),
  ]
    .filter(Boolean)
    .join(" — ");
}

/** By `ordem` — the server's order and the contract's numbering. */
export function ordenarPorOrdem<T extends { ordem: number }>(lista: readonly T[]): T[] {
  return [...lista].sort((a, b) => a.ordem - b.ordem);
}

/** `lista` with item `i` swapped one step (`delta` = -1 up, +1 down); `null`
 *  when the move would leave the list (first up / last down). */
export function moverNaLista<T>(lista: readonly T[], i: number, delta: -1 | 1): T[] | null {
  const j = i + delta;
  if (i < 0 || i >= lista.length || j < 0 || j >= lista.length) return null;
  const nova = [...lista];
  [nova[i], nova[j]] = [nova[j], nova[i]];
  return nova;
}
