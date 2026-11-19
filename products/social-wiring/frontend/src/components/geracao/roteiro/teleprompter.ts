/**
 * Teleprompter version of a roteiro: only the words the creator says aloud.
 *
 * A roteiro is stored as markdown, with each beat under a `## <nome do bloco>`
 * title (and, in some formatos, a bold-only label line such as `**Slide 1 — Capa**`).
 * The teleprompter version drops those structure lines, strips the markdown
 * emphasis markers and keeps one blank line between the spoken paragraphs.
 * A chat reels script marks its beats with a plain `(Gancho)` label (the chat
 * stores `**(Gancho)**` as `(Gancho)`): on its own line it is structure, leading
 * a spoken line it is dropped from that line.
 */

const TITULO = /^\s{0,3}#{1,6}\s/;
const ROTULO_NEGRITO = /^\s*(\*\*|__)[^*_]+(\*\*|__)\s*:?\s*$/;
const REGRA = /^\s*([-*_])(\s*\1){2,}\s*$/;
const BEAT = /^\(([^()\n]{1,40})\)\s*/;

export function roteiroParaTeleprompter(markdown: string): string {
  const paragrafos: string[] = [];
  let atual: string[] = [];
  const fechar = () => {
    if (atual.length) paragrafos.push(atual.join("\n"));
    atual = [];
  };

  for (const bruta of markdown.replace(/\r\n?/g, "\n").split("\n")) {
    if (TITULO.test(bruta) || ROTULO_NEGRITO.test(bruta) || REGRA.test(bruta)) {
      fechar();
      continue;
    }
    let linha = bruta
      .replace(/(\*\*|__)(.+?)\1/g, "$2")
      .replace(/(^|[^*\w])\*(?!\s)([^*\n]+?)\*(?!\w)/g, "$1$2")
      .replace(/^\s*>\s?/, "")
      .replace(/^\s*[-*+]\s+/, "")
      .trim();
    if (linha && BEAT.test(linha) && !linha.replace(BEAT, "")) {
      fechar(); // a beat label on its own line is structure, like a title
      continue;
    }
    linha = linha.replace(BEAT, "");
    if (!linha) {
      fechar();
      continue;
    }
    atual.push(linha);
  }
  fechar();
  return paragrafos.join("\n\n");
}
