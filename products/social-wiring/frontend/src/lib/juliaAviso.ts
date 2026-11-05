/**
 * Privacy-notice section blocks -> plain text, for the READ-ONLY notice on the Agente page.
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
