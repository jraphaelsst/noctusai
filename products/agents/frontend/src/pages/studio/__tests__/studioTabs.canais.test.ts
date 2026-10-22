import { describe, expect, it } from "vitest";
import { isTabVisibleForKind, visibleTabsFor } from "../studioTabs";

const acc = { isOrgAdmin: true, platformAdminHint: true };
const ids = (a: Parameters<typeof visibleTabsFor>[0]) => visibleTabsFor(a, acc).map((t) => t.id);

describe("Canais tab visibility", () => {
  it("follows the usa_canais flag, not the agent key", () => {
    expect(isTabVisibleForKind("canais", "runtime", true)).toBe(true);
    expect(isTabVisibleForKind("canais", "runtime", false)).toBe(false);
    expect(isTabVisibleForKind("canais", "dev-advisor", true)).toBe(false);
    expect(ids({ kind: "runtime", usa_canais: true })).toContain("canais");
    expect(ids({ kind: "runtime", usa_canais: false })).not.toContain("canais");
    // a platform-defined agent named "julia" without the flag has no Canais; any other key with it does
    expect(ids({ definition_scope: "plataforma", kind: "runtime", usa_canais: false })).not.toContain("canais");
    expect(ids({ definition_scope: "plataforma", kind: "runtime", usa_canais: true })).toContain("canais");
  });
});
