/**
 * `formatUsdCost` tests — Agent Studio CONTRACT.md §L "Controle de custo".
 * `null`/`undefined` must NEVER collapse into "US$0.00" — that would read as
 * "free" for a cost we simply never captured (the exact failure mode §L
 * exists to fix; see `utils.ts`'s doc comment).
 */
import { describe, expect, it } from "vitest";
import { formatUsdCost } from "@/lib/utils";

describe("formatUsdCost", () => {
  it("renders '—' for null/undefined, never '0' or 'US$0.00'", () => {
    expect(formatUsdCost(null)).toBe("—");
    expect(formatUsdCost(undefined)).toBe("—");
  });

  it("renders 2 decimals for round amounts that round-trip cleanly at 2dp", () => {
    expect(formatUsdCost(2)).toBe("US$2.00");
    expect(formatUsdCost(0.01)).toBe("US$0.01");
  });

  it("grows to 3-4 decimals rather than rounding a non-round figure away", () => {
    expect(formatUsdCost(0.1234)).toBe("US$0.1234");
    expect(formatUsdCost(0.0088)).toBe("US$0.0088");
    expect(formatUsdCost(0.0001)).toBe("US$0.0001");
  });

  it("renders an actual zero cost as 'US$0.00' (distinct from the null case above)", () => {
    expect(formatUsdCost(0)).toBe("US$0.00");
  });
});
