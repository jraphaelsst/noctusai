/**
 * busca — the `/coleta` search. Synthetic fixtures: these tests pin the
 * matching RULES (accent/case folding, street index, dedupe, minimum
 * length), not any município's real schedule.
 */
import { describe, expect, it } from "vitest";

import { buscar, diaDeHoje, normalizar, passaNoDia } from "../busca";
import type { Municipio } from "../tipos";

const base: Omit<Municipio, "slug" | "nome" | "rotas"> = {
  cobertura: "completa",
  resumo: "",
  ecopontos: [],
  outros: [],
  contatos: [],
  avisos: [],
  fontes: [],
};

const carapicuiba: Municipio = {
  ...base,
  slug: "carapicuiba",
  nome: "Carapicuíba",
  rotas: [
    { setor: "Setor 24 – Fazendinha (INT)", bairros: ["Nova Fazendinha", "Pontal da Fazendinha"], dias: ["seg", "qua", "sex"], tipo: "comum" },
    { setor: "Setor 25 – Fazendinha (Ext)", bairros: ["Jardim Ana Estela", "Vila Diva"], dias: ["ter", "qui", "sab"], tipo: "comum" },
  ],
  ruas: [
    { rua: "Estrada da Fazendinha", bairro: "Pousada dos Bandeirantes", setor: "Setor 24 – Fazendinha (INT)" },
    { rua: "Estrada da Fazendinha", bairro: "Jardim Ana Estela", setor: "Setor 25 – Fazendinha (Ext)" },
  ],
};

const osasco: Municipio = {
  ...base,
  slug: "osasco",
  nome: "Osasco",
  rotas: [{ bairros: ["Fazendinha"], dias: ["seg", "qua", "sex"], periodo: "diurno", tipo: "comum" }],
};

describe("normalizar", () => {
  it("folds accents, case and whitespace", () => {
    expect(normalizar("  Carapicuíba   SÁB ")).toBe("carapicuiba sab");
  });
});

describe("buscar", () => {
  it("ignores queries shorter than the minimum", () => {
    expect(buscar([carapicuiba], "fa")).toEqual([]);
  });

  it("matches bairros across municípios, accent-insensitively", () => {
    const r = buscar([carapicuiba, osasco], "fazendinha");
    const municipios = new Set(r.map((x) => x.municipio.slug));
    expect(municipios).toEqual(new Set(["carapicuiba", "osasco"]));
  });

  it("matches a street and resolves EVERY setor it belongs to", () => {
    const r = buscar([carapicuiba], "estrada da faz").filter((x) => x.rua);
    expect(r.map((x) => x.rota.setor)).toEqual([
      "Setor 24 – Fazendinha (INT)",
      "Setor 25 – Fazendinha (Ext)",
    ]);
  });

  it("does not repeat the same bairro/rota pair", () => {
    const r = buscar([carapicuiba], "vila diva");
    expect(r).toHaveLength(1);
  });

  it("returns nothing for an unknown place", () => {
    expect(buscar([carapicuiba, osasco], "atlantida")).toEqual([]);
  });
});

describe("dias", () => {
  it("maps Date#getDay to the Dia key (0 = domingo)", () => {
    expect(diaDeHoje(new Date(2026, 8, 27))).toBe("dom");
    expect(diaDeHoje(new Date(2026, 9, 2))).toBe("sex");
  });

  it("passaNoDia reads the rota's days", () => {
    expect(passaNoDia(carapicuiba.rotas[1], "qui")).toBe(true);
    expect(passaNoDia(carapicuiba.rotas[1], "sex")).toBe(false);
  });
});
