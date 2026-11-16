/**
 * Pure helpers for the unified chat's answers (Estruturas contract §6.5):
 * `(estrutura #N)` citations -> in-app links, only for allowed codes. The headline lines
 * are NOT derived here any more — the server parses them (`Mensagem.propostas`).
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
 * (the server only vouches for the codes it parsed; a `(estrutura #N + #M)` mix
 * is not rewritten — its estruturas are the proposta card's chips).
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
