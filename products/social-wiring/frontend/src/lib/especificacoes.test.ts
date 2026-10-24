/**
 * The FE catalogue accessors read the GENERATED snapshot
 * (`especificacoesCatalogo.json`, pinned to the backend's `CATALOGO` by
 * `backend/tests/modules/card_hub/test_especificacoes_catalogo_fe.py`).
 * These pin the FE side: the snapshot's shape, every eixo has a header, and
 * the toggle rules mirror `validar` (`requer` / `exclusiva_com`).
 */
import { describe, expect, it } from "vitest";

import catalogoJson from "./especificacoesCatalogo.json";
import {
  CATALOGO,
  EIXOS,
  EIXO_ROTULO,
  ESPECIFICACAO_BASE,
  agruparPorEixo,
  alternar,
  especificacoesDoCard,
  incoerencia,
  motivoBloqueio,
  ordenar,
} from "./especificacoes";

describe("generated catalogue snapshot", () => {
  it("is read verbatim — keys in catalogue order, the base first", () => {
    expect(CATALOGO.map((e) => e.chave)).toEqual(catalogoJson.catalogo.map((e) => e.chave));
    expect(CATALOGO[0].chave).toBe(ESPECIFICACAO_BASE);
    expect(CATALOGO.map((e) => e.chave)).toEqual([
      "compra_venda",
      "a_vista",
      "sinal_saldo",
      "financiamento_bancario",
      "fgts",
      "parcelas_diretas",
      "intermediarias",
      "confissao_divida",
      "permuta",
      "intermediacao",
    ]);
  });

  it("every eixo has a header and every spec an eixo", () => {
    for (const eixo of EIXOS) expect(EIXO_ROTULO[eixo]).toBeTruthy();
    for (const e of CATALOGO) expect(EIXOS).toContain(e.eixo);
  });

  it("exclusivity is declared on both sides; requer names real keys", () => {
    const chaves = new Set(CATALOGO.map((e) => e.chave));
    for (const e of CATALOGO) {
      for (const r of e.requer) expect(chaves.has(r)).toBe(true);
      for (const x of e.exclusiva_com) {
        expect(CATALOGO.find((o) => o.chave === x)?.exclusiva_com).toContain(e.chave);
      }
    }
  });
});

describe("grouping", () => {
  it("groups by eixo, catalogue order", () => {
    const grupos = agruparPorEixo();
    expect(grupos.map((g) => g.eixo)).toEqual(["base", "pagamento", "confissao", "permuta", "intermediacao"]);
    expect(grupos[1].itens.map((e) => e.chave)).toEqual([
      "a_vista",
      "sinal_saldo",
      "financiamento_bancario",
      "fgts",
      "parcelas_diretas",
      "intermediarias",
    ]);
    expect(grupos[1].rotulo).toBe("Pagamento");
  });
});

describe("requer / exclusiva_com", () => {
  it("the base can never be toggled", () => {
    expect(motivoBloqueio("compra_venda", ["compra_venda"])).toBe("Sempre incluída.");
    expect(alternar("compra_venda", ["compra_venda"])).toEqual(["compra_venda"]);
  });

  it("FGTS requires financiamento bancário; selecting it first is refused with the reason", () => {
    expect(motivoBloqueio("fgts", ["compra_venda"])).toBe("Requer Financiamento bancário.");
    expect(alternar("fgts", ["compra_venda"])).toEqual(["compra_venda"]);
    const comFin = alternar("financiamento_bancario", ["compra_venda"]);
    expect(alternar("fgts", comFin)).toEqual(["compra_venda", "financiamento_bancario", "fgts"]);
  });

  it("a required spec cannot be unchecked while its dependant is selected", () => {
    const sel = ["compra_venda", "financiamento_bancario", "fgts"];
    expect(motivoBloqueio("financiamento_bancario", sel)).toBe("Necessária para Uso de FGTS.");
    expect(alternar("financiamento_bancario", sel)).toEqual(sel);
  });

  it("à vista is exclusive with financing/direct facets — both directions", () => {
    expect(motivoBloqueio("financiamento_bancario", ["compra_venda", "a_vista"])).toBe(
      "Incompatível com À vista (recursos próprios).",
    );
    expect(motivoBloqueio("a_vista", ["compra_venda", "parcelas_diretas"])).toBe(
      "Incompatível com Parcelas diretas ao vendedor.",
    );
    // à vista + sinal is a coherent pair (the sinal is the multa base).
    expect(motivoBloqueio("sinal_saldo", ["compra_venda", "a_vista"])).toBeNull();
  });

  it("incoerencia mirrors validar", () => {
    expect(incoerencia(["compra_venda"])).toBeNull();
    expect(incoerencia(["a_vista"])).toContain("obrigatória");
    expect(incoerencia(["compra_venda", "fgts"])).toContain("requer");
    expect(incoerencia(["compra_venda", "a_vista", "financiamento_bancario"])).toContain("não podem");
    expect(incoerencia(["compra_venda", "xyz"])).toContain("desconhecida");
  });

  it("ordenar keeps catalogue order and drops unknown keys", () => {
    expect(ordenar(["permuta", "compra_venda", "nope"])).toEqual(["compra_venda", "permuta"]);
  });
});

describe("especificacoesDoCard", () => {
  it("null when no live contract stored a selection (legacy)", () => {
    expect(especificacoesDoCard(undefined)).toBeNull();
    expect(especificacoesDoCard([{ status: "rascunho", especificacoes: null }])).toBeNull();
    expect(especificacoesDoCard([{ status: "rascunho" }])).toBeNull();
  });

  it("union of live contracts, cancelled ones ignored", () => {
    expect(
      especificacoesDoCard([
        { status: "rascunho", especificacoes: ["compra_venda", "a_vista"] },
        { status: "cancelado", especificacoes: ["compra_venda", "intermediacao"] },
        { status: "assinado", especificacoes: ["compra_venda", "permuta"] },
      ]),
    ).toEqual(["compra_venda", "a_vista", "permuta"]);
  });
});
