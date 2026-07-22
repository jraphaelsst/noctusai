import { describe, expect, it } from "vitest";
import { formatCompactNumber, formatPercent, formatPercentDelta, PT_BR_MONTH_LABELS_SHORT } from "./formatters";

describe("formatCompactNumber", () => {
  it("passes through small numbers with pt-BR grouping", () => {
    expect(formatCompactNumber(999)).toBe((999).toLocaleString("pt-BR"));
  });

  it("K-suffixes thousands", () => {
    expect(formatCompactNumber(1500)).toBe("1.5K");
  });

  it("M-suffixes millions", () => {
    expect(formatCompactNumber(2_300_000)).toBe("2.3M");
  });

  it("treats null/undefined as 0, never as NaN or a crash", () => {
    expect(formatCompactNumber(null)).toBe((0).toLocaleString("pt-BR"));
    expect(formatCompactNumber(undefined)).toBe((0).toLocaleString("pt-BR"));
  });

  it("renders a non-finite value as an em dash rather than 'NaN' or 'Infinity'", () => {
    expect(formatCompactNumber(NaN)).toBe("—");
    expect(formatCompactNumber(Infinity)).toBe("—");
  });
});

describe("formatPercentDelta", () => {
  it("signs a positive delta with a leading +", () => {
    expect(formatPercentDelta(23.44)).toBe("+23.4%");
  });

  it("does not double-sign a negative delta", () => {
    expect(formatPercentDelta(-5)).toBe("-5.0%");
  });

  it("renders an exact zero as a resolved 0.0%, distinct from the null/'—' case upstream", () => {
    expect(formatPercentDelta(0)).toBe("0.0%");
  });
});

describe("formatPercent", () => {
  it("renders a pt-BR comma decimal", () => {
    expect(formatPercent(23.44)).toBe("23,4%");
  });
});

describe("PT_BR_MONTH_LABELS_SHORT", () => {
  it("has exactly 12 entries, Jan first, Dez last", () => {
    expect(PT_BR_MONTH_LABELS_SHORT).toHaveLength(12);
    expect(PT_BR_MONTH_LABELS_SHORT[0]).toBe("Jan");
    expect(PT_BR_MONTH_LABELS_SHORT[11]).toBe("Dez");
  });
});
