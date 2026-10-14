import { describe, expect, it } from "vitest";
import { isTabVisibleForKind } from "../studioTabs";

describe("Canais tab visibility", () => {
  it("only for the lead-imob runtime agent", () => {
    expect(isTabVisibleForKind("canais", "runtime", "lead-imob")).toBe(true);
    expect(isTabVisibleForKind("canais", "runtime", "isaia")).toBe(false);
    expect(isTabVisibleForKind("canais", "dev-advisor", "lead-imob")).toBe(false);
  });
});
