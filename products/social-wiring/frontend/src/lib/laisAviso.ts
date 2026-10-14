/**
 * Privacy-notice section blocks <-> plain text, for the Agente page editor.
 *
 * The wire shape is `blocks: ({p: string} | {ul: string[]})[]`. The editor shows
 * one textarea per section: paragraphs are separated by a blank line, and a run
 * of lines starting with "- " is a bullet list. Round-trips losslessly for any
 * well-formed blocks (a paragraph that itself starts with "- " is the one shape
 * text cannot express — it is read back as a list item, which is what the user
 * typing it means).
 */
import type { LaisAvisoSecao } from "@/hooks/useLaisAviso";

type Bloco = LaisAvisoSecao["blocks"][number];

export function blocosParaTexto(blocks: Bloco[]): string {
  return blocks
    .map((b) => ("ul" in b ? b.ul.map((i) => `- ${i}`).join("\n") : b.p))
    .join("\n\n");
}

export function textoParaBlocos(texto: string): Bloco[] {
  const blocos: Bloco[] = [];
  for (const bruto of texto.split(/\n\s*\n/)) {
    const linhas = bruto
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);
    if (linhas.length === 0) continue;
    if (linhas.every((l) => l.startsWith("- "))) {
      blocos.push({ ul: linhas.map((l) => l.slice(2).trim()).filter(Boolean) });
    } else {
      blocos.push({ p: linhas.join(" ") });
    }
  }
  return blocos;
}

/** `{link}` is mandatory in the first message (it carries the notice URL). */
export function contemLink(mensagem: string): boolean {
  return mensagem.includes("{link}");
}
