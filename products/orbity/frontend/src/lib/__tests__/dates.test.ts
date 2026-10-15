import { describe, it, expect } from "vitest";
import { toLocalInput, fromLocalInput, localDayKey } from "../dates";

// Built from LOCAL components so the assertions hold in any runner timezone.
const evening = new Date(2026, 5, 1, 21, 30); // 01/06 21:30 local (BRT evening = next day in UTC)

describe("local-time helpers", () => {
  it("toLocalInput shows the local wall clock, not the UTC slice", () => {
    expect(toLocalInput(evening.toISOString())).toBe("2026-06-01T21:30");
  });
  it("round-trips an edit without shifting the instant", () => {
    const iso = evening.toISOString();
    expect(fromLocalInput(toLocalInput(iso))).toBe(iso);
  });
  it("localDayKey groups by the local calendar day", () => {
    expect(localDayKey(evening.toISOString())).toBe("2026-06-01");
    expect(localDayKey(new Date(2026, 5, 1, 0, 5).toISOString())).toBe("2026-06-01");
  });
  it("handles empty / invalid input", () => {
    expect(toLocalInput(undefined)).toBe("");
    expect(toLocalInput("nope")).toBe("");
  });
});
