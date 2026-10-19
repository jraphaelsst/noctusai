import { describe, expect, it } from "vitest";

import { paraJulia } from "./RedirectLegacyLais";

describe("RedirectLegacyLais.paraJulia", () => {
  it("moves every pre-rename /lais URL under /julia and keeps the rest of the path", () => {
    expect(paraJulia("/lais")).toBe("/julia");
    expect(paraJulia("/lais/conversas")).toBe("/julia/conversas");
    expect(paraJulia("/lais/conversas/h/abc-123")).toBe("/julia/conversas/h/abc-123");
    expect(paraJulia("/lais/reengajamento/reguas/9")).toBe("/julia/reengajamento/reguas/9");
  });

  it("leaves other paths alone (no accidental prefix match)", () => {
    expect(paraJulia("/laisx/foo")).toBe("/laisx/foo");
    expect(paraJulia("/julia/conversas")).toBe("/julia/conversas");
  });
});
