/**
 * `dataOnlyFromPossibleUtcMidnight` — Bug 4 (prod card 755253934). See its
 * docblock in `./utils.ts` for the full root-cause narrative.
 */
import { describe, expect, it } from "vitest";
import { dataOnlyFromPossibleUtcMidnight, formatarDocumento, limparDocumento } from "./utils";

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

/**
 * `formatarDocumento`/`limparDocumento` — P1/883 (2026-09-25). Lifted from
 * `NegociacaoEstruturadaPanel.tsx` (recurrence rule N=2 — `TestemunhasSection.
 * tsx` needed the same CPF display formatting). See `./utils.ts`'s own
 * docblock.
 */
describe("limparDocumento", () => {
  it("strips CPF mask separators", () => {
    expect(limparDocumento("812.598.158-62")).toBe("81259815862");
  });

  it("strips CNPJ mask separators and uppercases (post-2026 alphanumeric CNPJ)", () => {
    expect(limparDocumento("11.222.333/0001-8a")).toBe("112223330001" + "8A");
  });

  it("is idempotent on an already-clean value", () => {
    expect(limparDocumento("81259815862")).toBe("81259815862");
  });
});

describe("formatarDocumento", () => {
  it("formats a raw 11-digit CPF with the standard mask", () => {
    expect(formatarDocumento("81259815862")).toBe("812.598.158-62");
  });

  it("formats a raw 14-char CNPJ with the standard mask", () => {
    expect(formatarDocumento("11222333000181")).toBe("11.222.333/0001-81");
  });

  it("is idempotent on an already-masked CPF — never double-masks", () => {
    expect(formatarDocumento("812.598.158-62")).toBe("812.598.158-62");
  });

  it("formats progressively for a partial in-progress CPF", () => {
    expect(formatarDocumento("812")).toBe("812");
    expect(formatarDocumento("812598")).toBe("812.598");
    expect(formatarDocumento("812598158")).toBe("812.598.158");
  });

  it("returns an empty string for empty input", () => {
    expect(formatarDocumento("")).toBe("");
  });
});
