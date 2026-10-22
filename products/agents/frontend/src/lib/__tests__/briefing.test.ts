import { describe, expect, it } from "vitest";
import { BRIEFING_VAZIO, KEY_RE, slugify, validarBriefing } from "../briefing";

describe("slugify", () => {
  it("strips accents, collapses separators and always satisfies the key pattern", () => {
    expect(slugify("  Atendente da Loja — SP! ")).toBe("atendente-da-loja-sp");
    expect(KEY_RE.test(slugify("Atendente da Loja"))).toBe(true);
    expect(slugify("x".repeat(100)).length).toBeLessThanOrEqual(63);
  });
});

describe("validarBriefing", () => {
  const ok = { ...BRIEFING_VAZIO, nome: "Bia", objetivo: "Atender os clientes", publico: "Clientes", canal: "web" as const };
  it("accepts the minimum and omits empty optionals", () => {
    const r = validarBriefing(ok);
    expect(r.errors).toEqual({});
    expect(r.briefing).toEqual({ nome: "Bia", objetivo: "Atender os clientes", publico: "Clientes", canal: "web", idioma: "pt-BR" });
  });
  it("mirrors the contract limits", () => {
    const r = validarBriefing({ ...ok, nome: "", objetivo: "curto", publico: "ab", canal: "", tom_de_voz: "t".repeat(301), limites: "l".repeat(1001), exemplos: "e".repeat(4001) });
    expect(Object.keys(r.errors).sort()).toEqual(["canal", "exemplos", "limites", "nome", "objetivo", "publico", "tom_de_voz"]);
    expect(r.briefing).toBeNull();
    expect(validarBriefing({ ...ok, objetivo: "o".repeat(601) }).errors.objetivo).toMatch(/máximo de 600/);
  });
});
