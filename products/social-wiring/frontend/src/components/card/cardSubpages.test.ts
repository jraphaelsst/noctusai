/**
 * cardSubpages.resolverDestino — what a plain-string `destino`
 * (`fontes_possiveis[].destino`, `GeracaoFaltando.sugestoes[].destino`)
 * resolves to: a real route, a card subpage's pt-BR label, or neither.
 */
import { describe, expect, it } from "vitest";

import { CARD_SUBPAGES, resolverDestino } from "./cardSubpages";

describe("CARD_SUBPAGES — registry order", () => {
  it("🔴 places Cônjuge directly ABOVE Vendedor — the owner's ask", () => {
    const keys = CARD_SUBPAGES.map((s) => s.key);
    const conjugeIdx = keys.indexOf("conjuge");
    const vendedorIdx = keys.indexOf("vendedor");
    expect(conjugeIdx).toBeGreaterThanOrEqual(0);
    expect(vendedorIdx).toBe(conjugeIdx + 1);
  });

  // P0c contract (`project-history/roadmaps/sw-drive-extraction-P0c-
  // contract.md` §F) — the new Empresas tab.
  it("registers an Empresas entry directly below Vendedor", () => {
    const keys = CARD_SUBPAGES.map((s) => s.key);
    const vendedorIdx = keys.indexOf("vendedor");
    const empresasIdx = keys.indexOf("empresas");
    expect(empresasIdx).toBeGreaterThanOrEqual(0);
    expect(empresasIdx).toBe(vendedorIdx + 1);
    expect(CARD_SUBPAGES.find((s) => s.key === "empresas")?.label).toBe("Empresas");
  });

  // Levantamento de Certidões.xlsx — the matriz tab, directly below Empresas.
  it("registers a Certidões entry directly below Empresas", () => {
    const keys = CARD_SUBPAGES.map((s) => s.key);
    const empresasIdx = keys.indexOf("empresas");
    const certidoesIdx = keys.indexOf("certidoes");
    expect(certidoesIdx).toBeGreaterThanOrEqual(0);
    expect(certidoesIdx).toBe(empresasIdx + 1);
    expect(CARD_SUBPAGES.find((s) => s.key === "certidoes")?.label).toBe("Certidões");
  });
});

describe("resolverDestino", () => {
  it("treats a leading-slash destino as a real SPA route", () => {
    expect(resolverDestino("/matriculas")).toEqual({ rota: "/matriculas", subpageLabel: null });
  });

  it("resolves a known CardSubpageKey to its pt-BR label, no route", () => {
    expect(resolverDestino("contratos")).toEqual({ rota: null, subpageLabel: "Contratos" });
    expect(resolverDestino("geral")).toEqual({ rota: null, subpageLabel: "Geral" });
  });

  it("resolves an unrecognized, non-route destino to neither", () => {
    expect(resolverDestino("algo_desconhecido")).toEqual({ rota: null, subpageLabel: null });
  });

  it("resolves null/undefined to neither", () => {
    expect(resolverDestino(null)).toEqual({ rota: null, subpageLabel: null });
    expect(resolverDestino(undefined)).toEqual({ rota: null, subpageLabel: null });
  });
});

describe("partesPjDoLado — PJ parties on the Comprador/Vendedor lists (§2.1)", () => {
  const base = {
    papel: "proprietario", ordem: 1, observacao: null, cliente: null, empresa: null,
    cliente_id: null, empresa_id: "e1", nome: "X LTDA", documento: "11222333000181",
  };
  const partes = [
    { ...base, parte_id: "p1", titular: false, rotulo: "VEND 1", lado: "vendedor", tipo_pessoa: "PJ" },
    { ...base, parte_id: "p2", titular: false, rotulo: "COMP 2", lado: "comprador", tipo_pessoa: "PJ" },
    { ...base, parte_id: "p3", titular: false, rotulo: "VEND 2", lado: "vendedor", tipo_pessoa: "PF", cliente_id: "c1", empresa_id: null },
    { ...base, parte_id: null, titular: true, rotulo: "COMP 1", lado: "comprador", tipo_pessoa: "PJ" },
  ] as never;

  it("keeps only the PJ, non-titular rows of the asked side", async () => {
    const { partesPjDoLado } = await import("./cardSubpages");
    expect(partesPjDoLado(partes, "vendedor").map((p) => p.parte_id)).toEqual(["p1"]);
    expect(partesPjDoLado(partes, "comprador").map((p) => p.parte_id)).toEqual(["p2"]);
    expect(partesPjDoLado(undefined, "vendedor")).toEqual([]);
  });
});
