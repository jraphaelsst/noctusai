/**
 * useImoveis — display-helper tests.
 *
 * Not the query hooks themselves (TanStack wiring is exercised by the page
 * tests); this covers the pure functions the CONTRACT's field surface leans
 * on: the amenity label map (every CONTRACT § 3 missing key), the
 * genuine-0-vs-null distinction, and the boolean/absent-amenity helpers.
 */
import { describe, expect, it } from "vitest";

import {
  caracteristicaLabel,
  caracteristicasAusentes,
  formatBool,
  formatCount,
  formatMetros,
} from "./useImoveis";

// ─── Amenity labels — CONTRACT § 3's missing-key list ──────────────────────

describe("caracteristicaLabel — CONTRACT § 3 missing keys", () => {
  const casos: [string, string][] = [
    ["cercaeletrica", "Cerca elétrica"],
    ["alarme", "Alarme"],
    ["antenaparabolica", "Antena parabólica"],
    ["aquecimentoeletrico", "Aquecimento elétrico"],
    ["calefacao", "Calefação"],
    ["porao", "Porão"],
    ["sotao", "Sótão"],
    ["patio", "Pátio"],
    ["gabinete", "Gabinete"],
    ["sala", "Sala"],
    ["salaestar", "Sala de estar"],
    ["estarintimo", "Estar íntimo"],
    ["banheiroauxiliar", "Banheiro auxiliar"],
    ["cozinhamontada", "Cozinha montada"],
    ["cozinhacomtanque", "Cozinha com tanque"],
    ["construcaoalvenaria", "Construção em alvenaria"],
    ["living", "Living"],
  ];

  it.each(casos)("labels %s as %s", (slug, esperado) => {
    expect(caracteristicaLabel(slug)).toBe(esperado);
  });

  it("still resolves the upstream-typo collision key (already covered pre-correction)", () => {
    // Backend merges "Dependenciade Empregada" (typo) and
    // "Dependencia De Empregada" into ONE slug via CARACTERISTICA_COLLISIONS
    // — both fold to the same value, so there is only one key to assert.
    expect(caracteristicaLabel("dependenciadeempregada")).toBe("Dependência de empregada");
  });

  it("still falls back gracefully for a genuinely unknown slug", () => {
    expect(caracteristicaLabel("umaAmenidadeNovaDoVista")).toBe("Uma Amenidade Nova Do Vista");
  });
});

// ─── The 0-vs-null distinction ──────────────────────────────────────────────

describe("formatCount — genuine 0 vs unknown", () => {
  it("renders a real 0 as '0', not '—'", () => {
    expect(formatCount(0)).toBe("0");
  });

  it("renders null as '—'", () => {
    expect(formatCount(null)).toBe("—");
  });

  it("renders a positive count normally", () => {
    expect(formatCount(3)).toBe("3");
  });
});

describe("formatBool — Sim/Não, never true/false, null hides the field", () => {
  it("renders true as 'Sim'", () => {
    expect(formatBool(true)).toBe("Sim");
  });

  it("renders false as 'Não' — a real false is a fact, not absence", () => {
    expect(formatBool(false)).toBe("Não");
  });

  it("renders null as null, not '—' — CONTRACT § 7: null hides the field", () => {
    expect(formatBool(null)).toBeNull();
  });
});

describe("formatMetros — linear measurement, distinct unit from formatArea", () => {
  it("appends 'm', not 'm²'", () => {
    expect(formatMetros(12)).toBe("12 m");
  });

  it("renders null as '—'", () => {
    expect(formatMetros(null)).toBe("—");
  });
});

// ─── caracteristicasAusentes — the "não possui" complement ─────────────────

describe("caracteristicasAusentes", () => {
  it("excludes present slugs and only returns known ones", () => {
    const presentes = ["piscina", "sauna"];
    const ausentes = caracteristicasAusentes(presentes);

    expect(ausentes).not.toContain("piscina");
    expect(ausentes).not.toContain("sauna");
    expect(ausentes).toContain("alarme");
    expect(ausentes).toContain("living");
  });

  it("returns every known slug when nothing is present", () => {
    const ausentes = caracteristicasAusentes([]);
    expect(ausentes.length).toBeGreaterThan(60);
  });

  it("is case-insensitive against the present list", () => {
    const ausentes = caracteristicasAusentes(["PISCINA"]);
    expect(ausentes).not.toContain("piscina");
  });
});
