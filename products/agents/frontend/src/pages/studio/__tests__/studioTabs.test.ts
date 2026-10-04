/** Agent Packages §D3 — tab visibility per agent kind. */
import { describe, expect, it } from "vitest";
import { STUDIO_TABS, isTabVisibleForKind } from "../studioTabs";

const visible = (kind: string) => STUDIO_TABS.filter((t) => isTabVisibleForKind(t.id, kind)).map((t) => t.id);

describe("isTabVisibleForKind", () => {
  it("runtime agents keep Clientes and never see Aprendizados", () => {
    expect(visible("runtime")).toContain("clientes");
    expect(visible("runtime")).not.toContain("aprendizados");
  });
  it("dev-advisors hide Clientes and show Aprendizados", () => {
    expect(visible("dev-advisor")).not.toContain("clientes");
    expect(visible("dev-advisor")).toContain("aprendizados");
  });
});
