/**
 * `resolvePeriodo` — the period→date-range math the Custos page's selector
 * drives. Pure function, no network, no TanStack — tests the boundary math
 * directly (this month / last 30 days / previous month), the part most
 * likely to drift off-by-one at a month edge.
 */
import { describe, it, expect } from "vitest";
import { resolvePeriodo } from "./useCustos";

describe("resolvePeriodo", () => {
  const hoje = new Date(Date.UTC(2026, 8, 21)); // 2026-09-21

  it("este_mes runs from the 1st of the current month through today", () => {
    expect(resolvePeriodo("este_mes", hoje)).toEqual({
      from: "2026-09-01",
      to: "2026-09-21",
    });
  });

  it("ultimos_30_dias is a rolling 30-day window ending today", () => {
    expect(resolvePeriodo("ultimos_30_dias", hoje)).toEqual({
      from: "2026-08-23",
      to: "2026-09-21",
    });
  });

  it("mes_anterior is the FULL previous calendar month, not a 30-day rollback", () => {
    expect(resolvePeriodo("mes_anterior", hoje)).toEqual({
      from: "2026-08-01",
      to: "2026-08-31",
    });
  });

  it("mes_anterior correctly rolls the year back in January", () => {
    const janeiro = new Date(Date.UTC(2027, 0, 10)); // 2027-01-10
    expect(resolvePeriodo("mes_anterior", janeiro)).toEqual({
      from: "2026-12-01",
      to: "2026-12-31",
    });
  });
});
