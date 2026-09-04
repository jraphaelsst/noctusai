/**
 * ImovelValoresSection — CONTRACT § 5.3.
 *
 * The derived monthly-cost line (condomínio + IPTU/12) only renders when
 * BOTH source values exist — a half-derived total understates the real
 * cost, which is worse than showing none.
 */
import { afterEach, describe, expect, it } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import ImovelValoresSection from "./ImovelValoresSection";

type Props = Parameters<typeof ImovelValoresSection>[0];

function props(overrides: Partial<Props> = {}): Props {
  return {
    valorVenda: null,
    valorLocacao: null,
    valorCondominio: null,
    valorIptu: null,
    ...overrides,
  };
}

async function render(overrides: Partial<Props> = {}) {
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  const view = rtl.render(React.createElement(ImovelValoresSection, props(overrides)));
  return { ...rtl, ...view };
}

describe("ImovelValoresSection", () => {
  it("renders nothing when every value is null", async () => {
    const { container } = await render();
    expect(container.firstChild).toBeNull();
  });

  it("does NOT show a derived monthly cost when only condomínio is present", async () => {
    const { queryByText } = await render({ valorCondominio: 500 });
    expect(queryByText("Custo mensal estimado")).toBeNull();
  });

  it("does NOT show a derived monthly cost when only IPTU is present", async () => {
    const { queryByText } = await render({ valorIptu: 1200 });
    expect(queryByText("Custo mensal estimado")).toBeNull();
  });

  it("shows the derived monthly cost (condomínio + IPTU/12) only when BOTH are present", async () => {
    const { getByText } = await render({ valorCondominio: 500, valorIptu: 1200 });
    // 500 + 1200/12 = 600
    expect(getByText("Custo mensal estimado")).toBeTruthy();
    expect(getByText(/R\$\s*600/)).toBeTruthy();
  });
});
