/**
 * The preview split must agree with the server, centavo for centavo.
 *
 * 🔴 EVERY EXPECTED VALUE HERE CAME OUT OF THE PYTHON, NOT OUT OF MY HEAD.
 * They were produced by running `card_hub.negociacao_service.calcular` on the
 * same inputs. That is what makes this a drift test rather than a restatement
 * of the TypeScript: if the two implementations ever diverge, this fails
 * instead of a payout being wrong.
 */
import { describe, it, expect } from "vitest";

import { preverCalculo, ratear } from "./negociacaoPreview";

const BASE = {
  tem_parceria: false,
  pct_parceria: "50",
  pct_agencia: "50",
  pct_agentes: "45",
  pct_captador: "5",
};

describe("preverCalculo — paridade com o backend", () => {
  it("R$ 850.000 a 6%, sem parceria", () => {
    expect(
      preverCalculo({ ...BASE, valor_negociado: "850000", pct_comissao: "6" }),
    ).toMatchObject({
      calculavel: true,
      comissao_total: "51000.00",
      parceria: "0.00",
      nossa_parte: "51000.00",
      agencia: "25500.00",
      agentes_total: "22950.00",
      captador_total: "2550.00",
    });
  });

  it("R$ 333.333,33 a 6,5% com parceria 50/50 — o centavo ímpar vai para a parceria", () => {
    // Both halves are exactly 10833.335; the tie-break is the index, so the
    // leftover centavo lands on the first slice. Getting this backwards is a
    // one-centavo error that only shows up in a reconciliation.
    expect(
      preverCalculo({
        ...BASE,
        valor_negociado: "333333.33",
        pct_comissao: "6.5",
        tem_parceria: true,
      }),
    ).toMatchObject({
      comissao_total: "21666.67",
      parceria: "10833.34",
      nossa_parte: "10833.33",
      agencia: "5416.66",
      agentes_total: "4875.00",
      captador_total: "541.67",
    });
  });

  it("divisão em três partes desiguais distribui os centavos que sobram", () => {
    expect(
      preverCalculo({
        ...BASE,
        valor_negociado: "100",
        pct_comissao: "3.333",
        pct_agencia: "33",
        pct_agentes: "33",
        pct_captador: "34",
      }),
    ).toMatchObject({
      comissao_total: "3.33",
      agencia: "1.10",
      agentes_total: "1.10",
      captador_total: "1.13",
    });
  });

  it("um único centavo de comissão não se perde nem se duplica", () => {
    expect(
      preverCalculo({
        ...BASE,
        valor_negociado: "1",
        pct_comissao: "1",
        tem_parceria: true,
      }),
    ).toMatchObject({
      comissao_total: "0.01",
      parceria: "0.01",
      nossa_parte: "0.00",
      agencia: "0.00",
    });
  });
});

describe("preverCalculo — quando não há o que calcular", () => {
  it("sem % de comissão não inventa zeros", () => {
    const r = preverCalculo({ ...BASE, valor_negociado: "850000", pct_comissao: "" });
    expect(r.calculavel).toBe(false);
    expect(r.comissao_total).toBeNull();
  });

  it("sem valor negociado não inventa zeros", () => {
    const r = preverCalculo({ ...BASE, valor_negociado: "", pct_comissao: "6" });
    expect(r.calculavel).toBe(false);
  });

  it("valor zero não é uma negociação de R$ 0,00", () => {
    expect(preverCalculo({ ...BASE, valor_negociado: "0", pct_comissao: "6" }).calculavel).toBe(
      false,
    );
  });

  it("texto ilegível não vira NaN na tela", () => {
    const r = preverCalculo({ ...BASE, valor_negociado: "abc", pct_comissao: "6" });
    expect(r.calculavel).toBe(false);
  });
});

describe("ratear", () => {
  it("as partes somam exatamente o total", () => {
    for (const total of [1, 7, 333, 51000_00, 999_999_99]) {
      for (const pesos of [[50, 45, 5], [33, 33, 34], [1, 1, 1], [70, 30]]) {
        const partes = ratear(total, pesos);
        expect(partes.reduce((a, b) => a + b, 0)).toBe(total);
      }
    }
  });

  it("um total de zero divide em zeros, não em NaN", () => {
    expect(ratear(0, [50, 45, 5])).toEqual([0, 0, 0]);
  });

  it("pesos zerados não dividem por zero", () => {
    expect(ratear(100, [0, 0, 0])).toEqual([0, 0, 0]);
  });
});
