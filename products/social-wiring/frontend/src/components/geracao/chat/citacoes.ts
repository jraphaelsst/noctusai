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

/**
 * The attention-trigger names the HEADLINE agent appends in parentheses (BE prompt
 * `chat_headline.py` + methodology triggers). Single source for stripping/detecting the tag.
 */
export const GATILHOS_TAG = [
  "Popularidade/Autoridade",
  "Recompensa",
  "Mistério",
  "Reconhecimento",
  "Crença",
  "Disrupção",
  "Autoridade",
  "Popularidade",
] as const;

const semAcento = (t: string) => t.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
const GATILHOS_NORM = new Set(GATILHOS_TAG.map(semAcento));
const TAG_FINAL_RE = /\s*\(\s*([^()]{3,40}?)\s*\)\s*[.!?]?\s*$/;

function tagFinal(texto: string): { corpo: string; tag: string } | null {
  const m = TAG_FINAL_RE.exec(texto);
  if (!m || !GATILHOS_NORM.has(semAcento(m[1]))) return null;
  return { corpo: texto.slice(0, m.index).trim(), tag: m[1] };
}

/** Removes a trailing attention-trigger tag, e.g. "Texto. (Recompensa)" -> "Texto." */
export function removerTagGatilho(texto: string): string {
  const t = tagFinal(texto.trim());
  return t && t.corpo ? t.corpo : texto.trim();
}

const MAX_PALAVRAS = 25;

/**
 * The headline lines of an answer. Only list items count (never paragraphs). When any item
 * carries a trigger tag (the contract format), only tagged items are headlines; otherwise
 * untagged items count unless they are questions or too long to be a hook.
 * Returned text is clean: no emphasis, no citation, no trigger tag.
 */
export function extrairHeadlines(texto: string): string[] {
  const itens: string[] = [];
  for (const linha of texto.split("\n")) {
    const m = ITEM_RE.exec(linha);
    if (!m) continue;
    const limpa = m[1]
      .replace(CITACAO_RE, "")
      .replace(/\*\*|__/g, "")
      .replace(/\s+/g, " ")
      .trim()
      .replace(/^["“]|["”]$/g, "")
      .trim();
    if (limpa.length >= 5) itens.push(limpa);
  }
  const comTag = itens.filter((i) => tagFinal(i));
  const base = comTag.length
    ? comTag
    : itens.filter((i) => !/\?\s*$/.test(i) && i.split(/\s+/).length <= MAX_PALAVRAS);
  const out: string[] = [];
  for (const i of base) {
    const h = removerTagGatilho(i).replace(/^["“]|["”]$/g, "").trim();
    if (h.length >= 5 && !out.includes(h)) out.push(h);
  }
  return out;
}
