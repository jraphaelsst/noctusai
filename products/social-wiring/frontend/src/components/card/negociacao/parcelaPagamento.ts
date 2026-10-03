/**
 * Pure helpers for the migration-192 parcela fields edited in
 * `ParcelaFormDialog` (contrato-pagamentos-CONTRACT §1): the split among
 * several favorecidos (`favorecidos_divisao`, by value OR by percentage) and
 * the FGTS part of the financing parcela (`valor_fgts`).
 *
 * The server only checks SHAPE on save (2+ shares, no repeats, value XOR
 * percentage, `valor_fgts < valor`); whether the shares add up is the
 * contract gate's (`DIVISAO_SOMA_DIVERGE`, …). So this module refuses only
 * what the server would refuse, and reports the reconciliation as
 * information — a draft that does not add up yet is legitimate.
 *
 * 🔴 Money stays a decimal STRING on the wire; `Number` is used only to
 * DISPLAY the reconciliation, never to compose a stored amount.
 */
import { lerValorDigitado } from "@/lib/moedaDecimal";
import type { ParcelaDivisaoIn } from "@/types/negociacaoEstruturada";

export type DivisaoModo = "valor" | "percentual";

export interface DivisaoLinha {
  uid: string;
  favorecido_id: string;
  /** What was typed — a pt-BR money value or a percentage. */
  texto: string;
}

/** `percentual` as typed: `50`, `33,33`, `33.33` → `"33.33"`. */
function lerPercentual(texto: string): string {
  return texto.trim().replace(/%/g, "").replace(",", ".").trim();
}

export function divisaoParaWire(modo: DivisaoModo, linhas: DivisaoLinha[]): ParcelaDivisaoIn[] {
  return linhas.map((l) => {
    const item: ParcelaDivisaoIn = { favorecido_id: l.favorecido_id };
    if (l.texto.trim() !== "") {
      if (modo === "valor") item.valor = lerValorDigitado(l.texto);
      else item.percentual = lerPercentual(l.texto);
    }
    return item;
  });
}

/** The pt-BR reasons the server would refuse this split (empty ⇒ saveable). */
export function errosDivisao(modo: DivisaoModo, linhas: DivisaoLinha[]): string[] {
  const erros: string[] = [];
  if (linhas.length < 2) erros.push("Divida entre pelo menos dois favorecidos.");
  if (linhas.some((l) => !l.favorecido_id)) erros.push("Escolha o favorecido de cada parte.");
  const ids = linhas.map((l) => l.favorecido_id).filter(Boolean);
  if (new Set(ids).size !== ids.length) erros.push("O mesmo favorecido aparece duas vezes.");
  for (const l of linhas) {
    if (l.texto.trim() === "") continue;
    const n = Number(modo === "valor" ? lerValorDigitado(l.texto) : lerPercentual(l.texto));
    if (!Number.isFinite(n) || n <= 0) {
      erros.push(modo === "valor" ? "Cada valor deve ser maior que zero." : "Cada percentual deve ser maior que zero.");
      break;
    }
    if (modo === "percentual" && n > 100) {
      erros.push("Nenhum percentual pode passar de 100%.");
      break;
    }
  }
  return erros;
}

export interface Conciliacao {
  /** Every share has a number typed. */
  completa: boolean;
  /** The shares match the target (the parcela's value, or 100%). */
  confere: boolean;
  /** pt-BR one-liner for the operator. */
  texto: string;
}

const brl = (n: number) => n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const pct = (n: number) => `${n.toLocaleString("pt-BR", { maximumFractionDigits: 4 })}%`;

/** DISPLAY-ONLY: do the shares add up? (The contract gate decides.) */
export function conciliarDivisao(
  modo: DivisaoModo,
  linhas: DivisaoLinha[],
  valorParcelaTexto: string,
): Conciliacao {
  const preenchidas = linhas.filter((l) => l.texto.trim() !== "");
  const completa = linhas.length > 0 && preenchidas.length === linhas.length;
  if (modo === "percentual") {
    const soma = preenchidas.reduce((acc, l) => acc + Number(lerPercentual(l.texto) || 0), 0);
    const confere = completa && Math.abs(soma - 100) < 1e-9;
    return {
      completa,
      confere,
      texto: confere ? "Os percentuais somam 100%." : `Os percentuais somam ${pct(soma)} — devem somar 100%.`,
    };
  }
  const alvo = Number(lerValorDigitado(valorParcelaTexto));
  const soma = preenchidas.reduce((acc, l) => acc + Number(lerValorDigitado(l.texto) || 0), 0);
  if (!Number.isFinite(alvo) || valorParcelaTexto.trim() === "") {
    return { completa, confere: false, texto: `As partes somam ${brl(soma)}.` };
  }
  const diferenca = Math.round((alvo - soma) * 100) / 100;
  const confere = completa && diferenca === 0;
  return {
    completa,
    confere,
    texto: confere
      ? `As partes somam ${brl(soma)}, o valor da parcela.`
      : diferenca > 0
        ? `As partes somam ${brl(soma)} — faltam ${brl(diferenca)} para o valor da parcela.`
        : `As partes somam ${brl(soma)} — excedem o valor da parcela em ${brl(-diferenca)}.`,
  };
}

/** `valor_fgts` must be below the parcela's value (the financed part is the
 *  difference) — the server's 422, mirrored. `null` = fine / not typed. */
export function erroValorFgts(valorFgtsTexto: string, valorTexto: string): string | null {
  if (valorFgtsTexto.trim() === "") return null;
  const fgts = Number(lerValorDigitado(valorFgtsTexto));
  if (!Number.isFinite(fgts) || fgts <= 0) return "O valor do FGTS deve ser maior que zero.";
  const total = Number(lerValorDigitado(valorTexto));
  if (Number.isFinite(total) && valorTexto.trim() !== "" && fgts >= total) {
    return "O FGTS deve ser menor que o valor da parcela (o restante é o financiado).";
  }
  return null;
}
