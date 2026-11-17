/**
 * Privacy-notice section blocks -> plain text, for the notice on the Agente page (read view + platform-admin editor).
 *
 * The wire shape is `blocks: ({p: string} | {ul: string[]})[]`. The editor shows
 * one textarea per section: paragraphs are separated by a blank line, and a run
 * of lines starting with "- " is a bullet list. Round-trips losslessly for any
 * well-formed blocks (a paragraph that itself starts with "- " is the one shape
 * text cannot express — it is read back as a list item, which is what the user
 * typing it means).
 */
import type { JuliaAvisoSecao } from "@/hooks/useJuliaAviso";

type Bloco = JuliaAvisoSecao["blocks"][number];

export function blocosParaTexto(blocks: Bloco[]): string {
  return blocks
    .map((b) => ("ul" in b ? b.ul.map((i) => `- ${i}`).join("\n") : b.p))
    .join("\n\n");
}

/** Inverse of `blocosParaTexto`: blank-line separated chunks; a chunk whose every line starts with "- " is a list. */
export function textoParaBlocos(texto: string): Bloco[] {
  return texto
    .split(/\n\s*\n/)
    .map((c) => c.trim())
    .filter(Boolean)
    .map((c): Bloco => {
      const linhas = c.split("\n").map((l) => l.trim()).filter(Boolean);
      return linhas.every((l) => l.startsWith("- ")) ? { ul: linhas.map((l) => l.slice(2).trim()) } : { p: c };
    });
}
