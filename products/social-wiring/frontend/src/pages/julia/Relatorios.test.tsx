/** Lais › Relatórios — tabs, operação/mês switching, bairro select, empty states. */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

const api = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));

import LaisRelatorios from "./Relatorios";

const IMOVEIS = {
  tipos: [{ tipo: "Apartamento", pct_leads: 60, pct_prateleira: 40 }],
  top_imoveis: [{ codigo: "AP1", tipo: "Apartamento", preco: 350000, leads: 7 }],
};
const BAIRROS = (desempenho: unknown = null) => ({
  top_bairros: [{ bairro: "Centro", leads: 9 }],
  bairros_disponiveis: ["Centro", "Jardins"],
  desempenho,
});
const DESEMP = {
  bairro: "Centro", mediana_preco: 420000, pct_por_tipo: [{ tipo: "Casa", pct: 30 }], melhor_quartos: 3,
  mais_buscados: [{ codigo: "CA9", tipo: "Casa", preco: 500000, leads: 4 }],
};

function setup(resp: (url: string) => unknown) {
  api.get.mockImplementation((url: string) => Promise.resolve({ data: resp(url) }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}><MemoryRouter><LaisRelatorios /></MemoryRouter></QueryClientProvider>,
  );
}
beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

describe("Relatórios page", () => {
  it("renders the Imóveis tab tables with default aluguel", async () => {
    setup(() => IMOVEIS);
    expect(await screen.findByTestId("rel-tipos")).toBeTruthy();
    expect(screen.getByText("60%")).toBeTruthy();
    expect(screen.getByText("AP1").closest("a")?.getAttribute("href")).toBe("/imoveis/AP1");
    expect(api.get.mock.calls[0][0]).toContain("operacao=aluguel");
    expect(api.get.mock.calls[0][0]).toContain("aba=imoveis");
  });

  it("switches operação and month, refetching with the new filters", async () => {
    setup(() => IMOVEIS);
    await screen.findByTestId("rel-tipos");
    fireEvent.change(screen.getByLabelText("Operação"), { target: { value: "compra" } });
    await waitFor(() => expect(api.get.mock.calls.some((c) => String(c[0]).includes("operacao=compra"))).toBe(true));
    fireEvent.change(screen.getByLabelText("Mês"), { target: { value: "2026-03" } });
    await waitFor(() => expect(api.get.mock.calls.some((c) => String(c[0]).includes("mes=2026-03"))).toBe(true));
  });

  it("switches to Bairros and selects a bairro", async () => {
    setup((url) => (url.includes("aba=bairros") ? BAIRROS(url.includes("bairro=Centro") ? DESEMP : null) : IMOVEIS));
    await screen.findByTestId("rel-tipos");
    fireEvent.click(screen.getByRole("tab", { name: "Bairros" }));
    expect(await screen.findByTestId("rel-bairro-vazio")).toBeTruthy();
    expect(screen.getByTestId("rel-bairros-lista").textContent).toContain("Centro: 9 leads");
    fireEvent.change(screen.getByLabelText("Bairro"), { target: { value: "Centro" } });
    const d = await screen.findByTestId("rel-desempenho");
    expect(d.textContent).toContain("3 quartos");
    expect(d.textContent).toContain("buscaram por Casa");
    expect(screen.getByText("CA9")).toBeTruthy();
  });

  it("shows the empty state for a month with no data", async () => {
    setup(() => ({ tipos: [], top_imoveis: [] }));
    expect(await screen.findByTestId("rel-vazio")).toBeTruthy();
  });

  it("shows the empty state on Bairros with no data", async () => {
    setup((url) => (url.includes("aba=bairros") ? { top_bairros: [], bairros_disponiveis: [], desempenho: null } : IMOVEIS));
    await screen.findByTestId("rel-tipos");
    fireEvent.click(screen.getByRole("tab", { name: "Bairros" }));
    expect(await screen.findByTestId("rel-vazio")).toBeTruthy();
  });

  it("shows an error with retry", async () => {
    api.get.mockRejectedValue(new Error("boom"));
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={qc}><MemoryRouter><LaisRelatorios /></MemoryRouter></QueryClientProvider>);
    expect(await screen.findByTestId("rel-erro")).toBeTruthy();
  });
});
