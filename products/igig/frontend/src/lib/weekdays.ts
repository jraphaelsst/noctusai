/**
 * Weekday recurrence bitmask — the orçamento item's `dias_semana`
 * (wave-2 contract: seg=1 ter=2 qua=4 qui=8 sex=16 sab=32 dom=64).
 *
 * The SERVER computes `quantidade_mensal` / `subtotal`; this module only
 * renders and edits the mask, plus a local estimate used to label an item
 * before the debounced `/calcular` answer lands (never shown as the total).
 */
export interface Weekday {
  bit: number;
  /** One-letter chip label (S T Q Q S S D). */
  letra: string;
  /** Short name for text frequency ("Seg, Qua, Sex × 1"). */
  curto: string;
  /** Accessible name. */
  nome: string;
}

export const WEEKDAYS: readonly Weekday[] = [
  { bit: 1, letra: "S", curto: "Seg", nome: "Segunda" },
  { bit: 2, letra: "T", curto: "Ter", nome: "Terça" },
  { bit: 4, letra: "Q", curto: "Qua", nome: "Quarta" },
  { bit: 8, letra: "Q", curto: "Qui", nome: "Quinta" },
  { bit: 16, letra: "S", curto: "Sex", nome: "Sexta" },
  { bit: 32, letra: "S", curto: "Sáb", nome: "Sábado" },
  { bit: 64, letra: "D", curto: "Dom", nome: "Domingo" },
] as const;

export const TODOS_OS_DIAS = 127;
export const DIAS_UTEIS = 1 | 2 | 4 | 8 | 16;

export function toggleDia(mask: number, bit: number): number {
  return (mask ^ bit) & TODOS_OS_DIAS;
}

export function temDia(mask: number, bit: number): boolean {
  return (mask & bit) !== 0;
}

export function contarDias(mask: number): number {
  let n = 0;
  for (const d of WEEKDAYS) if (temDia(mask, d.bit)) n += 1;
  return n;
}

/** Same formula as the server — for the pre-`/calcular` hint only. */
export function quantidadeMensalEstimada(item: {
  recorrente: boolean;
  dias_semana: number;
  qtd_por_dia: number;
  quantidade: number;
}): number {
  return item.recorrente ? contarDias(item.dias_semana) * item.qtd_por_dia * 4 : item.quantidade;
}

/** "Seg, Qua, Sex × 1" — the PDF's frequency text, reused on screen. */
export function descreverFrequencia(mask: number, qtdPorDia: number): string {
  const dias = WEEKDAYS.filter((d) => temDia(mask, d.bit)).map((d) => d.curto);
  if (dias.length === 0) return "Nenhum dia";
  const texto = dias.length === 7 ? "Todos os dias" : dias.join(", ");
  return `${texto} × ${qtdPorDia}`;
}
