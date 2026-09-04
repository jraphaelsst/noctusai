/**
 * ImovelComodidadesSection — CONTRACT § 5.8.
 *
 *   · Sim-only amenities are prominent chips.
 *   · `orientacao_solar` is its OWN group, not mixed into the amenity chips
 *     — CONTRACT § 3: solar orientation is NOT an amenity.
 *   · The "não possui" list is collapsed behind a disclosure by default.
 *   · The section renders nothing when there is nothing to show.
 */
import { afterEach, describe, expect, it } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import ImovelComodidadesSection from "./ImovelComodidadesSection";

async function render(caracteristicas: string[], orientacaoSolar: string[] = []) {
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  const view = rtl.render(
    React.createElement(ImovelComodidadesSection, { caracteristicas, orientacaoSolar }),
  );
  return { ...rtl, ...view };
}

describe("ImovelComodidadesSection", () => {
  it("renders nothing when there are no amenities and no orientation", async () => {
    const { container } = await render([]);
    expect(container.firstChild).toBeNull();
  });

  it("renders the Sim-only amenities as prominent chips", async () => {
    const { getByText } = await render(["piscina", "sauna"]);
    expect(getByText("Piscina")).toBeTruthy();
    expect(getByText("Sauna")).toBeTruthy();
  });

  it("splits orientação solar into its own group, distinct from the amenity chips", async () => {
    const { getByText } = await render(["piscina"], ["Norte", "Sul"]);

    expect(getByText("Orientação solar")).toBeTruthy();
    expect(getByText("Norte")).toBeTruthy();
    expect(getByText("Sul")).toBeTruthy();
  });

  it("renders the orientation group even with zero amenities", async () => {
    const { getByText, queryByText } = await render([], ["Leste"]);
    expect(getByText("Leste")).toBeTruthy();
    expect(queryByText("Possui (0)")).toBeNull();
  });

  it("collapses the 'não possui' list behind a disclosure by default", async () => {
    const { getByText, queryByText } = await render(["piscina"]);

    // A known-absent amenity (never passed as present) should not be
    // visible until the disclosure is opened.
    expect(queryByText("Alarme")).toBeNull();
    expect(getByText(/Não possui/)).toBeTruthy();
  });

  it("reveals the 'não possui' amenities once the disclosure is opened", async () => {
    const { getByText, fireEvent } = await render(["piscina"]);

    fireEvent.click(getByText(/Não possui/));

    expect(getByText("Alarme")).toBeTruthy();
  });
});
