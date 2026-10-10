/**
 * Pure helpers for the HEADLINE agent's answers (contract §6.3 / §7.2):
 * - `(estrutura #N)` citations -> in-app links, only for allowed codes;
 * - splitting an answer into its individual headline lines (save / roteiro actions).
 */

const CITACAO_RE = /\(\s*estrutura\s*#(\d+)\s*\)/gi;
export const HREF_ESTRUTURA = "./estrutura/";

/** Codes cited in the text, in order of appearance, deduplicated. */
export function codigosCitados(texto: string): number[] {
  const out: number[] = [];
  for (const m of texto.matchAll(CITACAO_RE)) {
    const n = Number(m[1]);
    if (!out.includes(n)) out.push(n);
  }
  return out;
}

/**
 * Rewrites `(estrutura #N)` into a markdown link the renderer hands to
 * `onNavigate`. When `permitidos` is given, any other code stays plain text
 * (the server only vouches for the codes of the context it assembled).
 */
export function linkarCitacoes(texto: string, permitidos?: ReadonlySet<number> | null): string {
  return texto.replace(CITACAO_RE, (inteiro, cod: string) => {
    const n = Number(cod);
    if (permitidos && !permitidos.has(n)) return inteiro;
    return `([estrutura #${n}](${HREF_ESTRUTURA}${n}))`;
  });
}

/** `./estrutura/12` -> 12 (null for any other href). */
export function codigoDoHref(href: string): number | null {
  const m = /^\.?\/?estrutura\/(\d+)$/.exec(href);
  return m ? Number(m[1]) : null;
}

const ITEM_RE = /^\s*(?:\d+[.)]|[-*•])\s+(.*\S)\s*$/;

/** The headline lines of an answer: list items, with markdown emphasis and citations removed. */
export function extrairHeadlines(texto: string): string[] {
  const out: string[] = [];
  for (const linha of texto.split("\n")) {
    const m = ITEM_RE.exec(linha);
    if (!m) continue;
    const limpa = m[1]
      .replace(CITACAO_RE, "")
      .replace(/\*\*|__/g, "")
      .replace(/^["“]|["”]$/g, "")
      .replace(/\s+/g, " ")
      .trim();
    if (limpa.length >= 5) out.push(limpa);
  }
  return out;
}
