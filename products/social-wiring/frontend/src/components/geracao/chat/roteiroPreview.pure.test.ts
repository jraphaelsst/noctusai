import { describe, expect, it } from "vitest";

import { previewRoteiro } from "./roteiroPreview";

describe("previewRoteiro", () => {
  it("reels é o roteiro falado inteiro", () => {
    expect(previewRoteiro("reels", "  Fala 1.\n\nFala 2.  ")).toEqual({ tipo: "falado", texto: "Fala 1.\n\nFala 2." });
  });

  it("carrossel: lista de slides pelos títulos **Slide N**", () => {
    const p = previewRoteiro("carrossel", "**Slide 1**\nCapa forte\n\n**Slide 2 — Prova**: texto dois\nmais\n\n**Slide 3**\nFecho");
    expect(p).toMatchObject({ tipo: "secoes", rotulo: "Slides", legenda: null });
    if (p.tipo !== "secoes") throw new Error("x");
    expect(p.secoes.map((s) => s.titulo)).toEqual(["Slide 1", "Slide 2 — Prova", "Slide 3"]);
    expect(p.secoes[1].texto).toBe("texto dois\nmais");
  });

  it("post: telas + legenda", () => {
    const p = previewRoteiro("post", "**Tela 1**\nGancho\n\n**Tela 2**\nCorpo\n\n**Legenda**\nTexto da legenda\n#tag");
    if (p.tipo !== "secoes") throw new Error("x");
    expect(p.rotulo).toBe("Telas");
    expect(p.secoes).toHaveLength(2);
    expect(p.legenda).toBe("Texto da legenda\n#tag");
  });

  it("stories: quadros", () => {
    const p = previewRoteiro("stories", "**Quadro 1**\nEnquete\n**Quadro 2**\nLink");
    if (p.tipo !== "secoes") throw new Error("x");
    expect(p.rotulo).toBe("Quadros");
    expect(p.secoes.map((s) => s.texto)).toEqual(["Enquete", "Link"]);
  });

  it("sem títulos reconhecíveis cai no texto inteiro (nada é descartado)", () => {
    expect(previewRoteiro("carrossel", "Só um bloco corrido")).toEqual({ tipo: "texto", texto: "Só um bloco corrido" });
  });

  it("título de outro formato não é seção (Tela em carrossel)", () => {
    expect(previewRoteiro("carrossel", "**Tela 1**\nx").tipo).toBe("texto");
  });
});
