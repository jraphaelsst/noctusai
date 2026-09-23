/**
 * `dataOnlyFromPossibleUtcMidnight` — Bug 4 (prod card 755253934). See its
 * docblock in `./utils.ts` for the full root-cause narrative.
 */
import { describe, expect, it } from "vitest";
import { dataOnlyFromPossibleUtcMidnight } from "./utils";

describe("dataOnlyFromPossibleUtcMidnight", () => {
  it("strips a UTC-midnight timestamp (Z) down to its bare date", () => {
    expect(dataOnlyFromPossibleUtcMidnight("2026-09-23T00:00:00Z")).toBe("2026-09-23");
  });

  it("strips a UTC-midnight timestamp (+00:00) down to its bare date", () => {
    expect(dataOnlyFromPossibleUtcMidnight("2026-09-23T00:00:00+00:00")).toBe("2026-09-23");
  });

  it("strips a UTC-midnight timestamp with fractional seconds", () => {
    expect(dataOnlyFromPossibleUtcMidnight("2026-09-23T00:00:00.000Z")).toBe("2026-09-23");
  });

  it("leaves a non-midnight timestamp untouched — a real event, not a date-only fact", () => {
    expect(dataOnlyFromPossibleUtcMidnight("2026-09-23T13:15:00Z")).toBe(
      "2026-09-23T13:15:00Z",
    );
  });

  it("leaves a naive (no-offset) midnight timestamp untouched — already parses as LOCAL time, no shift to correct", () => {
    expect(dataOnlyFromPossibleUtcMidnight("2026-09-23T00:00:00")).toBe(
      "2026-09-23T00:00:00",
    );
  });

  it("leaves an already-bare date string untouched — nothing to strip", () => {
    expect(dataOnlyFromPossibleUtcMidnight("2026-09-23")).toBe("2026-09-23");
  });

  it("leaves a non-ISO / garbage string untouched rather than throwing", () => {
    expect(dataOnlyFromPossibleUtcMidnight("not-a-date")).toBe("not-a-date");
  });
});
