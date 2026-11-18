/** roteiroParaTeleprompter: keeps only the spoken words of a roteiro. */
import { describe, expect, it } from "vitest";

import { roteiroParaTeleprompter } from "./teleprompter";

describe("roteiroParaTeleprompter", () => {
  it("drops the beat titles and keeps one blank line between spoken paragraphs", () => {
    const md = [
      "## Headline (capa)",
      "Ninguém prepara uma mãe para isso.",
      "",
      "## CTA de salvar",
      "Salva esse vídeo.",
      "",
      "",
      "## Identificação",
      "Se você sente que perdeu o seu lugar,",
      "esse vídeo é para você.",
    ].join("\n");
    expect(roteiroParaTeleprompter(md)).toBe(
      "Ninguém prepara uma mãe para isso.\n\nSalva esse vídeo.\n\nSe você sente que perdeu o seu lugar,\nesse vídeo é para você.",
    );
  });

  it("drops bold-only label lines and strips emphasis markers inside the text", () => {
    const md = "**Slide 1 — Capa**\nIsso **não** é drama, é *luto*.\n\n---\n- uma coisa não anula a outra";
    expect(roteiroParaTeleprompter(md)).toBe("Isso não é drama, é luto.\n\numa coisa não anula a outra");
  });

  it("keeps [placeholders] and normalizes CRLF", () => {
    expect(roteiroParaTeleprompter("## Valor\r\nFale com [nome da amiga] hoje.\r\n")).toBe("Fale com [nome da amiga] hoje.");
  });

  it("returns an empty string for a roteiro with only titles", () => {
    expect(roteiroParaTeleprompter("## Headline\n\n## CTA")).toBe("");
  });
});
