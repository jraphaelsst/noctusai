/**
 * ImovelComodosSection — CONTRACT § 5.4.
 *
 *   · A genuine 0 (dormitórios on a Terreno) reads "0", not "—".
 *   · The section hides entirely when every field is null.
 *   · Lavabo/Copa/Escritorio are DELIBERATELY absent (CONTRACT § 1
 *     correction) — asserting their absence guards against re-adding the
 *     shadowed columns as facts here.
 */
import { afterEach, describe, expect, it } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import ImovelComodosSection from "./ImovelComodosSection";

type Props = Parameters<typeof ImovelComodosSection>[0];

function props(overrides: Partial<Props> = {}): Props {
  return {
    dormitorios: null,
    suites: null,
    vagas: null,
    banheiroSocial: null,
    closet: null,
    ...overrides,
  };
}

async function render(overrides: Partial<Props> = {}) {
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  const view = rtl.render(React.createElement(ImovelComodosSection, props(overrides)));
  return { ...rtl, ...view };
}

describe("ImovelComodosSection", () => {
  it("renders nothing when every field is null", async () => {
    const { container } = await render();
    expect(container.firstChild).toBeNull();
  });

  it("renders a genuine 0 dormitórios as '0', not '—' (Terreno case)", async () => {
    const { getByText } = await render({ dormitorios: 0 });
    expect(getByText("0")).toBeTruthy();
  });

  it("renders a positive count normally", async () => {
    const { getByText } = await render({ dormitorios: 3, vagas: 2 });
    expect(getByText("3")).toBeTruthy();
    expect(getByText("2")).toBeTruthy();
  });

  it("renders banheiro social as Sim/Não, never true/false", async () => {
    const { getByText } = await render({ banheiroSocial: true });
    expect(getByText("Sim")).toBeTruthy();
  });

  it("hides banheiro social entirely when null, rather than showing a dash", async () => {
    const { queryByText } = await render({ dormitorios: 1 });
    expect(queryByText("Banheiro social")).toBeNull();
  });

  it("never renders Lavabo, Copa, or Escritório as facts here — CONTRACT § 1 correction", async () => {
    const { queryByText } = await render({ dormitorios: 1, suites: 1, vagas: 1, closet: 1 });
    expect(queryByText("Lavabo")).toBeNull();
    expect(queryByText("Copa")).toBeNull();
    expect(queryByText("Escritório")).toBeNull();
  });
});
