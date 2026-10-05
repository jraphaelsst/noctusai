import { describe, expect, it } from "vitest";

import { comporEvento, diasPorExtenso, inteiroPorExtenso, lerEvento } from "./eventoParcela";

describe("extenso — parity with backend inteiro_por_extenso", () => {
  it.each([
    [1, "um"], [2, "dois"], [10, "dez"], [11, "onze"], [15, "quinze"], [19, "dezenove"],
    [20, "vinte"], [21, "vinte e um"], [30, "trinta"], [45, "quarenta e cinco"], [60, "sessenta"],
    [90, "noventa"], [100, "cem"], [101, "cento e um"], [120, "cento e vinte"],
    [180, "cento e oitenta"], [200, "duzentos"], [365, "trezentos e sessenta e cinco"],
    [999, "novecentos e noventa e nove"],
  ])("%i", (n, t) => expect(inteiroPorExtenso(n)).toBe(t));
  it("dias", () => {
    expect(diasPorExtenso(1)).toBe("1 (um) dia corrido");
    expect(diasPorExtenso(90)).toBe("90 (noventa) dias corridos");
  });
});

describe("evento vocabulary", () => {
  it("composes the office phrasing and round-trips", () => {
    const e = comporEvento({ opcao: "prazo", dias: "30", texto: "" });
    expect(e).toBe(
      "com prazo máximo de pagamento de 30 (trinta) dias corridos, a contar da assinatura do presente instrumento",
    );
    expect(lerEvento(e)).toEqual({ opcao: "prazo", dias: "30", texto: "" });
    expect(lerEvento("no ato da assinatura do presente instrumento").opcao).toBe("assinatura");
    expect(lerEvento("concomitante com a escritura")).toEqual({ opcao: "concomitante", dias: "", texto: "a escritura" });
    expect(lerEvento("na entrega das chaves")).toEqual({ opcao: "outro", dias: "", texto: "na entrega das chaves" });
  });
  it("incomplete state composes to empty", () => {
    expect(comporEvento({ opcao: "prazo", dias: "", texto: "" })).toBe("");
    expect(comporEvento({ opcao: "prazo", dias: "0", texto: "" })).toBe("");
    expect(comporEvento({ opcao: "concomitante", dias: "", texto: " " })).toBe("");
  });
});
