import { describe, expect, it } from "vitest";

import { parseValorBR } from "./format";

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

  it("returns null for an empty string, never 0", () => {
    expect(parseValorBR("")).toBeNull();
    expect(parseValorBR("   ")).toBeNull();
  });

  it("returns null for unparseable text, never 0", () => {
    expect(parseValorBR("abc")).toBeNull();
    expect(parseValorBR("R$ 10")).toBeNull();
  });
});
