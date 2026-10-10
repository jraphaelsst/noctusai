import { describe, expect, it } from "vitest";

import { codigoDoHref, codigosCitados, extrairHeadlines, linkarCitacoes, removerTagGatilho } from "./citacoes";

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

  it("resposta realista: duas listas numeradas e parágrafo final -> só as headlines", () => {
    const t = [
      "Aqui vão opções para o seu WhatsApp:",
      "",
      "1. Me dê 10 minutos e seu WhatsApp responde lead sozinho. (Recompensa)",
      "2. O erro que faz seu lead sumir no WhatsApp. (Mistério)",
      "",
      "Mais duas, com outro ângulo:",
      "",
      "1. Você ainda responde cada lead à mão? (Reconhecimento)",
      "2. Quem automatiza vende mais. (Popularidade/Autoridade)",
      "",
      "Não recebi material de pesquisa, então usei só o perfil.",
      "Me diga qual é o formato do post que você quer?",
    ].join("\n");
    expect(extrairHeadlines(t)).toEqual([
      "Me dê 10 minutos e seu WhatsApp responde lead sozinho.",
      "O erro que faz seu lead sumir no WhatsApp.",
      "Você ainda responde cada lead à mão?",
      "Quem automatiza vende mais.",
    ]);
  });

  it("notas finais em bullet, sem tag, não viram headline quando há itens com tag", () => {
    const t = "1. Headline boa aqui. (Crença)\n- Não recebi material de pesquisa.\n- Me diga o formato do post?";
    expect(extrairHeadlines(t)).toEqual(["Headline boa aqui."]);
  });

  it("sem tags: perguntas são ignoradas, itens curtos ficam", () => {
    expect(extrairHeadlines("- Pare de postar sem estratégia\n- Qual formato você quer?")).toEqual([
      "Pare de postar sem estratégia",
    ]);
  });

  it("removerTagGatilho tira só tag de gatilho no fim", () => {
    expect(removerTagGatilho("Texto bom. (Recompensa)")).toBe("Texto bom.");
    expect(removerTagGatilho("Texto (Disrupcao)")).toBe("Texto");
    expect(removerTagGatilho("Texto (outra coisa)")).toBe("Texto (outra coisa)");
    expect(removerTagGatilho("(Recompensa)")).toBe("(Recompensa)");
  });
});
