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

  it("drops the plain (Beat) labels of a chat reels script, on their own line or leading a spoken line", () => {
    const md = "(Gancho)\nVocê sabia que 9 em cada 10 erram?\n\n(Virada) Hoje eu te mostro o caminho.\n**(CTA)** Salva esse vídeo.";
    expect(roteiroParaTeleprompter(md)).toBe(
      "Você sabia que 9 em cada 10 erram?\n\nHoje eu te mostro o caminho.\nSalva esse vídeo.",
    );
  });

  it("keeps parentheses in the middle of a spoken line", () => {
    expect(roteiroParaTeleprompter("Isso dura (em média) oito horas.")).toBe("Isso dura (em média) oito horas.");
  });

  it("keeps [placeholders] and normalizes CRLF", () => {
    expect(roteiroParaTeleprompter("## Valor\r\nFale com [nome da amiga] hoje.\r\n")).toBe("Fale com [nome da amiga] hoje.");
  });

  it("returns an empty string for a roteiro with only titles", () => {
    expect(roteiroParaTeleprompter("## Headline\n\n## CTA")).toBe("");
  });
});
