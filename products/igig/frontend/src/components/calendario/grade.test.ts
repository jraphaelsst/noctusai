/**
 * Month-grid arithmetic (smoke finding 6: no weekday headers, no offset — day
 * 1 always sat in the first column). Monday-first.
 */
import { describe, expect, it } from "vitest";

import { celulasDoMes, deslocamentoInicial, diasNoMes, DIAS_SEMANA_CURTOS, isoLocal } from "./grade";

describe("deslocamentoInicial (Monday-first)", () => {
  it("is 0 when the month starts on a Monday", () => {
    expect(deslocamentoInicial(2026, 5)).toBe(0); // 2026-06-01 is a Monday
  });

  it("is 6 when the month starts on a Sunday", () => {
    expect(deslocamentoInicial(2026, 1)).toBe(6); // 2026-02-01 is a Sunday
  });

  it("is 2 when the month starts on a Wednesday", () => {
    expect(deslocamentoInicial(2026, 3)).toBe(2); // 2026-04-01 is a Wednesday
  });

  it("is 1 for September 2026 (starts on a Tuesday)", () => {
    expect(deslocamentoInicial(2026, 8)).toBe(1);
  });
});

describe("celulasDoMes", () => {
  it("pads the start so day 1 lands under its weekday header", () => {
    const celulas = celulasDoMes(2026, 3); // April 2026, starts Wednesday
    expect(celulas.slice(0, 3)).toEqual([null, null, 1]);
    expect(DIAS_SEMANA_CURTOS[celulas.indexOf(1)]).toBe("Qua");
  });

  it("always renders whole weeks", () => {
    for (let mes = 0; mes < 12; mes++) {
      expect(celulasDoMes(2026, mes).length % 7).toBe(0);
    }
  });

  it("contains every day of the month exactly once, in order", () => {
    const dias = celulasDoMes(2024, 1).filter((d): d is number => d !== null); // leap Feb
    expect(dias).toEqual(Array.from({ length: 29 }, (_, i) => i + 1));
    expect(diasNoMes(2024, 1)).toBe(29);
  });

  it("needs no padding at all for a Monday-first 28-day February", () => {
    expect(celulasDoMes(2027, 1)).toEqual(Array.from({ length: 28 }, (_, i) => i + 1)); // 2027-02-01 Monday
  });
});

describe("isoLocal", () => {
  it("formats in local time, not UTC", () => {
    expect(isoLocal(new Date(2026, 0, 5, 23, 30))).toBe("2026-01-05");
  });
});
