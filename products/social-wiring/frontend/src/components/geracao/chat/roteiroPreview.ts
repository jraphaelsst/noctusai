/**
 * Pure preview of a roteiro's markdown per formato (Estruturas contract §11.3): reels is a
 * spoken script (shown whole); carrossel / post / stories are split by their
 * `**Slide N**` / `**Tela N**` / `**Quadro N**` headings; a post's `**Legenda**` section is the caption.
 * Anything that does not parse falls back to the whole text — the preview never drops content.
 */
import type { EstruturaFormato } from "@/types/estruturas";

export type PreviewSecao = { titulo: string; texto: string };
export type PreviewRoteiro =
  | { tipo: "falado"; texto: string }
  | { tipo: "secoes"; rotulo: "Slides" | "Telas" | "Quadros"; secoes: PreviewSecao[]; legenda: string | null }
  | { tipo: "texto"; texto: string };

const ROTULO_SECAO: Record<Exclude<EstruturaFormato, "reels">, "Slides" | "Telas" | "Quadros"> = {
  carrossel: "Slides",
  post: "Telas",
  stories: "Quadros",
};
const TERMO_SECAO: Record<Exclude<EstruturaFormato, "reels">, string> = {
  carrossel: "Slide",
  post: "Tela",
  stories: "Quadro",
};

const esc = (t: string) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

export function previewRoteiro(formato: EstruturaFormato, conteudo: string): PreviewRoteiro {
  const texto = conteudo.trim();
  if (formato === "reels") return { tipo: "falado", texto };

  const termo = TERMO_SECAO[formato];
  // A heading line: optional `#`s, bold `Termo N` (+ optional title) and an optional trailing `:` + inline text.
  const cabecalho = new RegExp(`^\\s*(?:#{1,6}\\s*)?\\*\\*\\s*(${esc(termo)}\\s*\\d+[^*]*?)\\s*\\*\\*\\s*:?\\s*(.*)$`, "i");
  const legendaRe = /^\s*(?:#{1,6}\s*)?\*\*\s*Legenda[^*]*\*\*\s*:?\s*(.*)$/i;

  const secoes: PreviewSecao[] = [];
  let legenda: string[] | null = null;
  let atual: { titulo: string; linhas: string[] } | null = null;
  let emLegenda = false;
  const fechar = () => {
    if (atual) secoes.push({ titulo: atual.titulo.replace(/:$/, ""), texto: atual.linhas.join("\n").trim() });
    atual = null;
  };

  for (const linha of texto.split("\n")) {
    const l = legendaRe.exec(linha);
    if (l) {
      fechar();
      emLegenda = true;
      legenda = l[1] ? [l[1]] : [];
      continue;
    }
    const h = cabecalho.exec(linha);
    if (h) {
      fechar();
      emLegenda = false;
      atual = { titulo: h[1].trim(), linhas: h[2] ? [h[2]] : [] };
      continue;
    }
    if (emLegenda) legenda?.push(linha);
    else atual?.linhas.push(linha);
  }
  fechar();

  if (secoes.length === 0) return { tipo: "texto", texto };
  return {
    tipo: "secoes",
    rotulo: ROTULO_SECAO[formato],
    secoes,
    legenda: legenda ? (legenda as string[]).join("\n").trim() || null : null,
  };
}
