import { describe, expect, it } from "vitest";
import { isTabVisibleForKind } from "../studioTabs";

describe("Canais tab visibility", () => {
  it("only for the julia runtime agent", () => {
    expect(isTabVisibleForKind("canais", "runtime", "julia")).toBe(true);
    expect(isTabVisibleForKind("canais", "runtime", "isaia")).toBe(false);
    expect(isTabVisibleForKind("canais", "dev-advisor", "julia")).toBe(false);
  });
});
