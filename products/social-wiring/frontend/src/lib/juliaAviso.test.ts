import { describe, expect, it } from "vitest";

import { blocosParaTexto, contemLink, textoParaBlocos } from "@/lib/juliaAviso";

describe("juliaAviso block text codec", () => {
  it("round-trips paragraphs and bullet lists", () => {
    const blocks = [{ p: "Tratamos seus dados." }, { ul: ["nome", "telefone"] }, { p: "Fim." }];
    expect(textoParaBlocos(blocosParaTexto(blocks))).toEqual(blocks);
  });

  it("joins soft-wrapped lines of one paragraph and drops empty blocks", () => {
    expect(textoParaBlocos("linha um\nlinha dois\n\n\n\n")).toEqual([{ p: "linha um linha dois" }]);
    expect(textoParaBlocos("   \n\n  ")).toEqual([]);
  });

  it("contemLink requires the literal {link} placeholder", () => {
    expect(contemLink("Olá! Veja {link}")).toBe(true);
    expect(contemLink("Olá! Sem link")).toBe(false);
  });
});
