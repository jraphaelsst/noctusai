/**
 * resumo — the condensing layer of `/coleta`: day labels, plain-word
 * periods, grouping by day pattern and merging a search hit's comum +
 * seletiva lines. Synthetic fixtures only.
 */
import { describe, expect, it } from "vitest";

import { agruparPorDias, agruparResultados, diasCurtos, diasPorExtenso, periodoLegivel, resumoRota } from "../resumo";
import type { Municipio, Rota } from "../tipos";

describe("day labels", () => {
  it("abbreviates and spells out", () => {
    expect(diasCurtos(["sex", "seg", "qua"])).toBe("Seg · Qua · Sex");
    expect(diasPorExtenso(["ter", "qui", "sab"])).toBe("Terça, quinta e sábado");
    expect(diasPorExtenso(["qui"])).toBe("Quinta");
  });

  it("collapses full runs", () => {
    const segSab = ["seg", "ter", "qua", "qui", "sex", "sab"] as const;
    expect(diasCurtos([...segSab])).toBe("Seg a Sáb");
    expect(diasPorExtenso([...segSab])).toBe("Segunda a sábado");
  });
});

describe("periodoLegivel", () => {
  it("translates source jargon to plain words", () => {
    expect(periodoLegivel("diurno")).toBe("de dia");
    expect(periodoLegivel("noturno (a partir das 19h)")).toBe("à noite, a partir das 19h");
    expect(periodoLegivel("manhã/tarde")).toBe("manhã e tarde");
    expect(periodoLegivel("06h–16h")).toBe("06h–16h");
    expect(periodoLegivel(undefined)).toBeUndefined();
  });
});

describe("agruparPorDias", () => {
  const rotas: Rota[] = [
    { setor: "S1", bairros: ["A", "B"], dias: ["seg", "qua", "sex"], periodo: "diurno", tipo: "comum" },
    { setor: "S2", bairros: ["B", "C"], dias: ["seg", "qua", "sex"], periodo: "diurno", tipo: "comum", nota: "n1" },
    { setor: "S3", bairros: ["D"], dias: ["ter", "qui", "sab"], periodo: "noturno", tipo: "comum" },
    { setor: "S4", bairros: ["E"], dias: [], frequencia: "diário", tipo: "comum" },
    { bairros: ["F"], dias: ["qui"], tipo: "seletiva" },
  ];

  it("merges setores sharing days + period, de-duplicating bairros", () => {
    const g = agruparPorDias(rotas, "comum");
    expect(g).toHaveLength(3);
    expect(g[0]).toMatchObject({ dias: ["seg", "qua", "sex"], periodo: "de dia", bairros: ["A", "B", "C"], notas: ["n1"] });
  });

  it("orders day shifts before night shifts on the same days", () => {
    const g = agruparPorDias(
      [
        { bairros: ["N"], dias: ["seg"], periodo: "noturno", tipo: "comum" },
        { bairros: ["D"], dias: ["seg"], periodo: "diurno", tipo: "comum" },
      ],
      "comum",
    );
    expect(g.map((x) => x.periodo)).toEqual(["de dia", "à noite"]);
  });

  it("puts groups without known days last", () => {
    const g = agruparPorDias(rotas, "comum");
    expect(g[g.length - 1].frequencia).toBe("diário");
  });

  it("filters by tipo", () => {
    expect(agruparPorDias(rotas, "seletiva")).toHaveLength(1);
  });
});

describe("agruparResultados + resumoRota", () => {
  const m = { slug: "x", nome: "X" } as Municipio;
  const comum: Rota = { bairros: ["Centro"], dias: ["seg", "qua", "sex"], periodo: "noturno", tipo: "comum" };
  const seletiva: Rota = { bairros: ["Centro"], dias: ["qui"], tipo: "seletiva" };

  it("merges comum + seletiva hits for the same place into one answer", () => {
    const [local, ...resto] = agruparResultados([
      { municipio: m, rota: comum, termo: "Centro" },
      { municipio: m, rota: seletiva, termo: "Centro" },
    ]);
    expect(resto).toHaveLength(0);
    expect(local.comum).toEqual([comum]);
    expect(local.seletiva).toEqual([seletiva]);
  });

  it("reads as one line", () => {
    expect(resumoRota(comum)).toBe("Seg · Qua · Sex, à noite");
    expect(resumoRota({ bairros: [], dias: [], frequencia: "diário", tipo: "comum" })).toBe("diário");
  });
});
