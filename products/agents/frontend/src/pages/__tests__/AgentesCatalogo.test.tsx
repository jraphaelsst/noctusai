/** AgentesCatalogo page — synthetic placeholder content only (owner IP rule). */
import React from "react";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockUse = vi.fn();
vi.mock("@/hooks/useAgentesCatalogo", () => ({ useAgentesCatalogo: () => mockUse() }));

const SDR = { key: "agente-sdr", nome: "Agente SDR", papel: "sdr", descricao_publica: "Descrição sintética A.", runtime: "internal", capacidades: ["Capacidade Alfa", "Capacidade Beta"] };
const OPERADOR = { key: "agente-op", nome: "Agente Operador", papel: "operador", descricao_publica: "Descrição sintética B.", runtime: "external", capacidades: ["Capacidade Gama"] };

beforeEach(() => {
  vi.clearAllMocks();
  mockUse.mockReturnValue({ data: [SDR, OPERADOR], showSkeleton: false, isRefreshing: false, isError: false });
});
afterEach(() => cleanup());

async function renderPage() {
  const Page = (await import("@/pages/AgentesCatalogo")).default;
  render(React.createElement(Page));
}

describe("AgentesCatalogo", () => {
  it("renders one card per agent with papel, runtime and chips", async () => {
    await renderPage();
    expect(screen.getByTestId("catalogo-card-agente-sdr")).toBeTruthy();
    expect(screen.getByTestId("catalogo-card-agente-op")).toBeTruthy();
    expect(screen.getByTestId("catalogo-papel-agente-sdr").textContent).toBe("SDR / leads");
    expect(screen.getByTestId("catalogo-runtime-agente-op").textContent).toBe("Externo");
    expect(screen.getByText("Capacidade Alfa")).toBeTruthy();
    expect(screen.getByText("Descrição sintética B.")).toBeTruthy();
  });

  it("filters by papel", async () => {
    await renderPage();
    fireEvent.click(screen.getByTestId("catalogo-filtro-operador"));
    expect(screen.queryByTestId("catalogo-card-agente-sdr")).toBeNull();
    expect(screen.getByTestId("catalogo-card-agente-op")).toBeTruthy();
  });

  it("shows the empty state", async () => {
    mockUse.mockReturnValue({ data: [], showSkeleton: false, isRefreshing: false, isError: false });
    await renderPage();
    expect(screen.getByTestId("catalogo-empty")).toBeTruthy();
  });

  it("shows the error state", async () => {
    mockUse.mockReturnValue({ data: undefined, showSkeleton: false, isRefreshing: false, isError: true });
    await renderPage();
    expect(screen.getByTestId("catalogo-error")).toBeTruthy();
  });

  it("shows the skeleton while pending", async () => {
    mockUse.mockReturnValue({ data: undefined, showSkeleton: true, isRefreshing: false, isError: false });
    await renderPage();
    expect(screen.getByTestId("catalogo-skeleton")).toBeTruthy();
  });

  it("hides admin-only fields when absent", async () => {
    await renderPage();
    expect(screen.queryByTestId("catalogo-ferramentas-agente-sdr")).toBeNull();
    expect(screen.queryByTestId("catalogo-versao-agente-sdr")).toBeNull();
  });

  it("shows admin-only fields when present", async () => {
    mockUse.mockReturnValue({
      data: [{ ...SDR, ferramentas: ["ferramenta_x"], versao_ativa: 3, versoes: [{ versao: 3, status: "ativa" }] }],
      showSkeleton: false, isRefreshing: false, isError: false,
    });
    await renderPage();
    expect(screen.getByText("ferramenta_x")).toBeTruthy();
    expect(screen.getByTestId("catalogo-versao-agente-sdr").textContent).toContain("3");
  });
});
