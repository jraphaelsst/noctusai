/** ImovelMetadadosSection — a date-only value must render as the same calendar day (no UTC shift). */
import { afterEach, describe, expect, it } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import ImovelMetadadosSection from "./ImovelMetadadosSection";

describe("ImovelMetadadosSection", () => {
  it("shows a date-only 'Cadastrado em' as that same calendar day", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(
      <ImovelMetadadosSection
        dataCadastro="2026-10-21"
        dataAtualizacao="2026-10-01"
        diasDesdeAtualizacao={20}
        sincronizadoEm={null}
      />,
    );
    expect(screen.getByText("21/10/2026")).toBeTruthy();
    expect(screen.getByText(/01\/10\/2026 \(há 20 dias\)/)).toBeTruthy();
  });
});
