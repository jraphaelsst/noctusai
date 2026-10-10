import { describe, expect, it } from "vitest";

import { codigoDoHref, codigosCitados, extrairHeadlines, linkarCitacoes } from "./citacoes";

describe("citacoes", () => {
  it("liga (estrutura #N) a um href interno", () => {
    expect(linkarCitacoes("Teste (estrutura #42)")).toBe("Teste ([estrutura #42](./estrutura/42))");
  });

  it("só liga códigos permitidos; os demais ficam texto puro", () => {
    const out = linkarCitacoes("A (estrutura #1) B (estrutura #2)", new Set([1]));
    expect(out).toContain("[estrutura #1](./estrutura/1)");
    expect(out).toContain("(estrutura #2)");
    expect(out).not.toContain("./estrutura/2");
  });

  it("codigoDoHref só aceita o href de estrutura", () => {
    expect(codigoDoHref("./estrutura/7")).toBe(7);
    expect(codigoDoHref("https://x.com/estrutura/7")).toBeNull();
    expect(codigoDoHref("#a")).toBeNull();
  });

  it("codigosCitados deduplica na ordem", () => {
    expect(codigosCitados("(estrutura #3) (estrutura #1) (estrutura #3)")).toEqual([3, 1]);
  });

  it("extrai headlines de itens de lista, sem ênfase nem citação", () => {
    const t = [
      "Aqui vão:",
      "1. **Você erra isso** (estrutura #9)",
      "2) “Segunda headline boa”",
      "- Terceira, em bullet",
      "texto solto que não é item",
      "- ok",
    ].join("\n");
    expect(extrairHeadlines(t)).toEqual(["Você erra isso", "Segunda headline boa", "Terceira, em bullet"]);
  });
});
