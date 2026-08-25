/**
 * Painel — the landing screen that replaced the YouTube dashboard.
 *
 * The finding this closes: a real-estate agency logging in saw four empty
 * channel-metric cards and "Nenhum canal conectado". These pin that the
 * replacement shows the business, and that each tile leads somewhere.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const mockUsePainel = vi.fn();
vi.mock("@/hooks/usePainel", () => ({ usePainel: mockUsePainel }));

vi.mock("react-router-dom", () => ({
  Link: ({ to, children, ...rest }: any) => (
    <a href={to} {...rest}>
      {children}
    </a>
  ),
}));

const PAINEL = {
  novos: 12,
  parados: 7,
  agendamentos: 3,
  revisao: 270,
  em_negociacao: 1_850_000,
  proximos_agendamentos: [
    {
      atendimento_id: "a1",
      cliente_id: "c1",
      titulo: "Compra do apto",
      quando: "2026-08-27T14:00:00+00:00",
      tipo: "visita",
    },
  ],
  atendimentos_parados: [
    {
      atendimento_id: "a2",
      cliente_id: "c2",
      titulo: "Terreno Granja",
      quando: "2026-07-01T10:00:00+00:00",
      tipo: null,
    },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  mockUsePainel.mockReturnValue({
    data: PAINEL,
    loading: false,
    isError: false,
    refetch: vi.fn(),
  });
});

async function render() {
  const React = (await import("react")).default;
  const { default: Dashboard } = await import("./Dashboard");
  const rtl = await import("@testing-library/react");
  return rtl.render(React.createElement(Dashboard));
}

describe("Painel", () => {
  it("shows the five numbers a person can act on", async () => {
    const { getByTestId } = await render();

    expect(getByTestId("painel-tile-novos").textContent).toContain("12");
    expect(getByTestId("painel-tile-parados").textContent).toContain("7");
    expect(getByTestId("painel-tile-agenda").textContent).toContain("3");
    expect(getByTestId("painel-tile-revisao").textContent).toContain("270");
  });

  it("formats money as BRL rather than a bare number", async () => {
    const { getByTestId } = await render();

    const tile = getByTestId("painel-tile-negociacao").textContent ?? "";
    expect(tile).toContain("R$");
    expect(tile).toContain("1.850.000");
  });

  it("every tile leads to the screen where the work happens", async () => {
    // A number nobody can act on is decoration — which is exactly what this
    // route used to be.
    const { getByTestId } = await render();

    expect(getByTestId("painel-tile-parados").getAttribute("href")).toBe("/funil");
    expect(getByTestId("painel-tile-revisao").getAttribute("href")).toBe(
      "/clientes/revisao",
    );
  });

  it("says nothing about YouTube", async () => {
    // 🔴 The regression pin. This page's whole defect was being about a
    // channel that does not exist.
    const { container } = await render();

    expect(container.textContent).not.toMatch(/youtube|canal|inscritos|v[íi]deos/i);
  });

  it("lists what is booked and what has gone quiet", async () => {
    const { getByText } = await render();

    expect(getByText("Compra do apto")).toBeTruthy();
    expect(getByText("Terreno Granja")).toBeTruthy();
  });

  it("an empty agenda reads as good news, not as an error", async () => {
    mockUsePainel.mockReturnValue({
      data: { ...PAINEL, proximos_agendamentos: [], atendimentos_parados: [] },
      loading: false,
      isError: false,
      refetch: vi.fn(),
    });

    const { getByText } = await render();

    expect(getByText(/Nenhum atendimento esquecido/)).toBeTruthy();
  });

  it("shows a skeleton before the first payload, not an empty panel", async () => {
    mockUsePainel.mockReturnValue({
      data: undefined,
      loading: true,
      isError: false,
      refetch: vi.fn(),
    });

    const { getByTestId } = await render();

    expect(getByTestId("painel-loading")).toBeTruthy();
  });

  it("offers a retry when the panel cannot load", async () => {
    const refetch = vi.fn();
    mockUsePainel.mockReturnValue({
      data: undefined,
      loading: false,
      isError: true,
      refetch,
    });

    const { getByTestId } = await render();
    const rtl = await import("@testing-library/react");
    rtl.fireEvent.click(getByTestId("painel-retry"));

    expect(refetch).toHaveBeenCalled();
  });
});
