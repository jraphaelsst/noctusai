/**
 * Office phrasings of a parcela's `evento` (counts over 93 signed contracts:
 * "no ato da assinatura do presente instrumento" 73 vs 0 for "do contrato";
 * the "prazo máximo … a contar da assinatura do presente instrumento" 67 vs 2).
 *
 * The generator prints `evento` verbatim, so the UI must write the exact
 * phrasing. The vocabulary SHOULD be backend-owned (generator + UI agreeing);
 * until an endpoint exists it lives here, with `diasPorExtenso` mirroring the
 * backend's `noctusai_lib.domain.texto_ptbr.dias_por_extenso` (parity-tested).
 */

const UNI = ["", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez",
  "onze", "doze", "treze", "quatorze", "quinze", "dezesseis", "dezessete", "dezoito", "dezenove"];
const DEZ = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta", "noventa"];
const CEN = ["", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos", "seiscentos",
  "setecentos", "oitocentos", "novecentos"];

/** 1..999 in masculine cardinal, same wording as the backend. */
export function inteiroPorExtenso(n: number): string {
  if (!Number.isInteger(n) || n < 1 || n > 999) throw new RangeError("1..999");
  if (n === 100) return "cem";
  const c = Math.floor(n / 100);
  const r = n % 100;
  const partes: string[] = [];
  if (c) partes.push(CEN[c]);
  if (r) {
    if (r < 20) partes.push(UNI[r]);
    else {
      partes.push(DEZ[Math.floor(r / 10)]);
      if (r % 10) partes.push(UNI[r % 10]);
    }
  }
  return partes.join(" e ");
}

/** `90` -> "90 (noventa) dias corridos"; `1` -> "1 (um) dia corrido". */
export function diasPorExtenso(n: number): string {
  return n === 1 ? "1 (um) dia corrido" : `${n} (${inteiroPorExtenso(n)}) dias corridos`;
}

export type EventoOpcaoId = "assinatura" | "prazo" | "financiamento" | "concomitante" | "outro";

export const EVENTO_ASSINATURA = "no ato da assinatura do presente instrumento";
export const EVENTO_FINANCIAMENTO = "por ocasião da assinatura do Contrato de Financiamento Imobiliário";
const PRAZO_PREFIXO = "com prazo máximo de pagamento de ";
const PRAZO_SUFIXO = ", a contar da assinatura do presente instrumento";
const CONCOMITANTE_PREFIXO = "concomitante com ";

export const EVENTO_OPCOES: { id: EventoOpcaoId; rotulo: string }[] = [
  { id: "assinatura", rotulo: "No ato da assinatura do contrato" },
  { id: "prazo", rotulo: "Prazo máximo de N dias a contar da assinatura" },
  { id: "financiamento", rotulo: "Na assinatura do Contrato de Financiamento" },
  { id: "concomitante", rotulo: "Concomitante com…" },
  { id: "outro", rotulo: "Outro (texto livre)" },
];

export interface EventoEstado {
  opcao: EventoOpcaoId | "";
  dias: string;
  texto: string;
}

export const MAX_DIAS = 999;

export function diasValidos(dias: string): number | null {
  const n = Number(dias);
  return /^\d+$/.test(dias.trim()) && n >= 1 && n <= MAX_DIAS ? n : null;
}

/** The `evento` string for a picker state; `""` when the state is incomplete. */
export function comporEvento(e: EventoEstado): string {
  switch (e.opcao) {
    case "assinatura":
      return EVENTO_ASSINATURA;
    case "financiamento":
      return EVENTO_FINANCIAMENTO;
    case "prazo": {
      const n = diasValidos(e.dias);
      return n === null ? "" : `${PRAZO_PREFIXO}${diasPorExtenso(n)}${PRAZO_SUFIXO}`;
    }
    case "concomitante":
      return e.texto.trim() ? `${CONCOMITANTE_PREFIXO}${e.texto.trim()}` : "";
    case "outro":
      return e.texto.trim();
    default:
      return "";
  }
}

/** Reverse of `comporEvento`: a stored string -> picker state (unknown ⇒ "outro"). */
export function lerEvento(evento: string | null | undefined): EventoEstado {
  const v = (evento ?? "").trim();
  if (!v) return { opcao: "", dias: "", texto: "" };
  if (v === EVENTO_ASSINATURA) return { opcao: "assinatura", dias: "", texto: "" };
  if (v === EVENTO_FINANCIAMENTO) return { opcao: "financiamento", dias: "", texto: "" };
  const m = /^com prazo máximo de pagamento de (\d+) \(.+\) dias? corridos?, a contar da assinatura do presente instrumento$/.exec(v);
  if (m && diasValidos(m[1]) !== null && comporEvento({ opcao: "prazo", dias: m[1], texto: "" }) === v) {
    return { opcao: "prazo", dias: m[1], texto: "" };
  }
  if (v.startsWith(CONCOMITANTE_PREFIXO) && v.length > CONCOMITANTE_PREFIXO.length) {
    return { opcao: "concomitante", dias: "", texto: v.slice(CONCOMITANTE_PREFIXO.length) };
  }
  return { opcao: "outro", dias: "", texto: v };
}
