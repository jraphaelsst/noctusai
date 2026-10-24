/**
 * The contract SPECIFICATION catalogue, FE side (CONTRACT.md §10).
 *
 * 🔴 SINGLE SOURCE: the vocabulary is the backend's
 * (`contrato_gerador/especificacoes.py::CATALOGO`). `especificacoesCatalogo.json`
 * is GENERATED from it and pinned equal by the backend test
 * `tests/modules/card_hub/test_especificacoes_catalogo_fe.py` (regenerate
 * with `NOCTUS_REGENERAR_CATALOGO_FE=1`). Nothing here re-types a key, a label
 * or a rule — the only FE-owned strings are the eixo HEADERS (presentation),
 * and `especificacoes.test.ts` fails if an eixo has none.
 *
 * The rules below mirror `validar` so the picker never offers a selection the
 * PUT refuses: `requer` (a spec needs another one selected) and
 * `exclusiva_com` (two specs that cannot coexist). The server still decides —
 * a 400 is shown verbatim.
 */
import catalogoJson from "./especificacoesCatalogo.json";

export interface EspecificacaoDef {
  chave: string;
  rotulo: string;
  eixo: string;
  requer: string[];
  exclusiva_com: string[];
}

interface CatalogoArquivo {
  versao: number;
  base: string;
  eixos: string[];
  catalogo: EspecificacaoDef[];
}

const ARQUIVO = catalogoJson as CatalogoArquivo;

export const CATALOGO_VERSAO: number = ARQUIVO.versao;
export const ESPECIFICACAO_BASE: string = ARQUIVO.base;
export const EIXOS: readonly string[] = ARQUIVO.eixos;
export const CATALOGO: readonly EspecificacaoDef[] = ARQUIVO.catalogo;
export const POR_CHAVE: Readonly<Record<string, EspecificacaoDef>> = Object.fromEntries(
  CATALOGO.map((e) => [e.chave, e]),
);

/** Group headers — presentation only; keyed by the generated `EIXOS`. */
export const EIXO_ROTULO: Readonly<Record<string, string>> = {
  base: "Base",
  pagamento: "Pagamento",
  confissao: "Confissão de dívida",
  permuta: "Permuta",
  intermediacao: "Intermediação",
};

export function rotuloEspecificacao(chave: string): string {
  return POR_CHAVE[chave]?.rotulo ?? chave;
}

/** The catalogue grouped by eixo, catalogue order inside each group. */
export function agruparPorEixo(): { eixo: string; rotulo: string; itens: EspecificacaoDef[] }[] {
  return EIXOS.map((eixo) => ({
    eixo,
    rotulo: EIXO_ROTULO[eixo] ?? eixo,
    itens: CATALOGO.filter((e) => e.eixo === eixo),
  })).filter((g) => g.itens.length > 0);
}

/** Catalogue order, unknown keys dropped (same normalisation as `validar`). */
export function ordenar(chaves: Iterable<string>): string[] {
  const conjunto = new Set(chaves);
  return CATALOGO.map((e) => e.chave).filter((c) => conjunto.has(c));
}

export function mesmasEspecificacoes(a: readonly string[], b: readonly string[]): boolean {
  const x = ordenar(a);
  const y = ordenar(b);
  return x.length === y.length && x.every((c, i) => c === y[i]);
}

/**
 * Why `chave` cannot be toggled from `selecao` right now — `null` when it
 * can. The reason is the sentence the picker shows next to the disabled box.
 */
export function motivoBloqueio(chave: string, selecao: readonly string[]): string | null {
  const def = POR_CHAVE[chave];
  if (!def) return null;
  const sel = new Set(selecao);
  if (chave === ESPECIFICACAO_BASE) return "Sempre incluída.";
  if (sel.has(chave)) {
    // Unchecking: refused while another selected spec requires it.
    const dependentes = CATALOGO.filter((e) => sel.has(e.chave) && e.requer.includes(chave));
    if (dependentes.length > 0) {
      return `Necessária para ${dependentes.map((e) => e.rotulo).join(", ")}.`;
    }
    return null;
  }
  const exclusoras = def.exclusiva_com.filter((x) => sel.has(x));
  if (exclusoras.length > 0) {
    return `Incompatível com ${exclusoras.map(rotuloEspecificacao).join(", ")}.`;
  }
  const faltam = def.requer.filter((r) => !sel.has(r));
  if (faltam.length > 0) {
    return `Requer ${faltam.map(rotuloEspecificacao).join(", ")}.`;
  }
  return null;
}

/** Toggle `chave` when allowed; otherwise returns the selection unchanged. */
export function alternar(chave: string, selecao: readonly string[]): string[] {
  if (motivoBloqueio(chave, selecao) !== null) return ordenar(selecao);
  const sel = new Set(selecao);
  if (sel.has(chave)) sel.delete(chave);
  else sel.add(chave);
  return ordenar(sel);
}

/** The FE mirror of `validar` — the first incoherence, or `null`. */
export function incoerencia(selecao: readonly string[]): string | null {
  const desconhecida = selecao.find((c) => !POR_CHAVE[c]);
  if (desconhecida) return `Especificação desconhecida: ${desconhecida}.`;
  const sel = new Set(selecao);
  if (!sel.has(ESPECIFICACAO_BASE)) return `${rotuloEspecificacao(ESPECIFICACAO_BASE)} é obrigatória.`;
  for (const chave of ordenar(sel)) {
    const def = POR_CHAVE[chave];
    for (const r of def.requer) {
      if (!sel.has(r)) return `${def.rotulo} requer ${rotuloEspecificacao(r)}.`;
    }
    for (const x of def.exclusiva_com) {
      if (sel.has(x)) return `${def.rotulo} e ${rotuloEspecificacao(x)} não podem ser combinadas.`;
    }
  }
  return null;
}

/**
 * The specifications that scope a CARD's negociação (a card may carry more
 * than one contract): the union of every live (non-cancelled) contract's
 * stored selection. `null` when no live contract stored one — legacy mode,
 * nothing is scoped (every subtab shows).
 */
export function especificacoesDoCard(
  contratos: readonly { status: string; especificacoes?: string[] | null }[] | undefined,
): string[] | null {
  const vivos = (contratos ?? []).filter((c) => c.status !== "cancelado" && Array.isArray(c.especificacoes));
  if (vivos.length === 0) return null;
  return ordenar(vivos.flatMap((c) => c.especificacoes as string[]));
}
