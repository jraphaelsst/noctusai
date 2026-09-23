import { describe, expect, it } from "vitest";

import {
  DIAS_UTEIS,
  TODOS_OS_DIAS,
  WEEKDAYS,
  contarDias,
  descreverFrequencia,
  quantidadeMensalEstimada,
  temDia,
  toggleDia,
} from "./weekdays";

describe("weekday bitmask (contract: seg=1 … dom=64)", () => {
  it("uses the contract's bit per day, Monday first", () => {
    expect(WEEKDAYS.map((d) => d.bit)).toEqual([1, 2, 4, 8, 16, 32, 64]);
    expect(WEEKDAYS.map((d) => d.letra).join(" ")).toBe("S T Q Q S S D");
  });

  it("toggles a single day without touching the others", () => {
    const segQuaSex = 1 | 4 | 16;
    expect(toggleDia(segQuaSex, 4)).toBe(1 | 16);
    expect(toggleDia(1 | 16, 4)).toBe(segQuaSex);
    expect(temDia(segQuaSex, 2)).toBe(false);
  });

  it("never escapes the 7-day mask", () => {
    expect(toggleDia(TODOS_OS_DIAS, 128)).toBe(TODOS_OS_DIAS);
  });

  it("counts days", () => {
    expect(contarDias(0)).toBe(0);
    expect(contarDias(DIAS_UTEIS)).toBe(5);
    expect(contarDias(TODOS_OS_DIAS)).toBe(7);
  });

  it("estimates the monthly quantity with the server's formula", () => {
    // recorrente: popcount × qtd/dia × 4
    expect(quantidadeMensalEstimada({ recorrente: true, dias_semana: 1 | 4 | 16, qtd_por_dia: 2, quantidade: 99 })).toBe(24);
    // one-off: quantidade
    expect(quantidadeMensalEstimada({ recorrente: false, dias_semana: 127, qtd_por_dia: 5, quantidade: 3 })).toBe(3);
  });

  it("describes a frequency like the PDF does", () => {
    expect(descreverFrequencia(1 | 4 | 16, 1)).toBe("Seg, Qua, Sex × 1");
    expect(descreverFrequencia(TODOS_OS_DIAS, 2)).toBe("Todos os dias × 2");
    expect(descreverFrequencia(0, 1)).toBe("Nenhum dia");
  });
});
