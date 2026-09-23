/**
 * cardSubpages.resolverDestino — what a plain-string `destino`
 * (`fontes_possiveis[].destino`, `GeracaoFaltando.sugestoes[].destino`)
 * resolves to: a real route, a card subpage's pt-BR label, or neither.
 */
import { describe, expect, it } from "vitest";

import { resolverDestino } from "./cardSubpages";

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
