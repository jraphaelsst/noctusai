import { describe, expect, it } from "vitest";

import { horasBR, numeroBR, parseValorBR, pct } from "./format";

describe("parseValorBR", () => {
  it("parses a comma-decimal amount", () => {
    expect(parseValorBR("1500,00")).toBe(1500);
  });

  it("parses a pt-BR thousands separator with a comma decimal (finding #5)", () => {
    expect(parseValorBR("1.500,00")).toBe(1500);
  });

  it("parses a plain decimal with no comma", () => {
    expect(parseValorBR("1500.00")).toBe(1500);
  });

  it("parses a bare integer", () => {
    expect(parseValorBR("1500")).toBe(1500);
  });

  it("a pt-BR thousands separator WITHOUT a decimal part (tech-lead addendum, 2026-09)", () => {
    // Before this fix, no comma meant "read as-is" — Number("1.500") is 1.5,
    // silently undercharging a R$ 1.500,00 item typed without the cents.
    expect(parseValorBR("1.500")).toBe(1500);
  });

  it("multiple thousands groups without a decimal part", () => {
    expect(parseValorBR("1.500.000")).toBe(1500000);
  });

  it("still reads a short decimal fraction as a decimal, not thousands", () => {
    expect(parseValorBR("1500.5")).toBe(1500.5);
  });

  it("returns null for an empty string, never 0", () => {
    expect(parseValorBR("")).toBeNull();
    expect(parseValorBR("   ")).toBeNull();
  });

  it("returns null for unparseable text, never 0", () => {
    expect(parseValorBR("abc")).toBeNull();
    expect(parseValorBR("R$ 10")).toBeNull();
  });
});

describe("pct", () => {
  it("uses a pt-BR comma, never an American decimal point", () => {
    expect(pct(52.8)).toBe("52,8%");
  });
});

describe("numeroBR", () => {
  it("uses a pt-BR comma with the requested decimal places", () => {
    expect(numeroBR(0.5)).toBe("0,50");
    expect(numeroBR(1.256, 2)).toBe("1,26");
  });
});

describe("horasBR", () => {
  it("renders a pt-BR comma and the 'h' unit", () => {
    expect(horasBR(12.5)).toBe("12,5 h");
    expect(horasBR(1)).toBe("1 h");
  });
});
