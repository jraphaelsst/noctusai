/**
 * Clientes page (Slice F): the listing's four states, opening the card by
 * click and by `?id=` deep link, and "Novo cliente" (POST, then the new
 * cliente's card opens). The card itself has its own test
 * (`components/clientes/__tests__/ClienteCardDialog.test.tsx`); here it is
 * stubbed to expose which cliente it was opened for.
 */
/// <reference types="@testing-library/jest-dom" />
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import "@testing-library/jest-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

const { api } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn(), upload: vi.fn() },
}));
vi.mock("@noctusai/seed/infra", () => ({ api }));
vi.mock("@/components/clientes/ClienteCardDialog", () => ({
  ClienteCardDialog: ({ clienteId, onClose }: { clienteId: string | null; onClose: () => void }) =>
    clienteId ? (
      <div data-testid="card-stub">
        card de {clienteId}
        <button type="button" onClick={onClose}>
          fechar card
        </button>
      </div>
    ) : null,
}));
vi.mock("@/components/orcamento/OrcamentoModal", () => ({ OrcamentoModal: () => null }));

import Clientes from "../Clientes";

const C1 = {
  id: "c1", org_id: "org", nome: "Padaria Sol", nicho: "Alimentação", email: "sol@padaria.com", telefone: null,
  status: "ativo", origem: null, observacoes: null, created_at: "2026-09-01T10:00:00Z", updated_at: null,
};
const C2 = { ...C1, id: "c2", nome: "Oficina Lua", nicho: null, email: null, status: "prospect" };

function renderPage(url = "/clientes") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[url]}>
        <Clientes />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.get.mockImplementation(async (path: string) => {
    if (path === "/api/clientes") return { itens: [C1, C2], total: 2 };
    throw new Error(`GET inesperado ${path}`);
  });
  api.post.mockResolvedValue({ ...C1, id: "c9", nome: "Nova Loja" });
});
afterEach(cleanup);

describe("Clientes page", () => {
  it("lists clientes as mobile cards and as a desktop table", async () => {
    renderPage();
    const cards = await screen.findByTestId("clientes-cards");
    expect(within(cards).getByText("Padaria Sol")).toBeInTheDocument();
    expect(within(screen.getByTestId("clientes-tabela")).getByText("Oficina Lua")).toBeInTheDocument();
    expect(screen.getByText("2 clientes")).toBeInTheDocument();
  });

  it("clicking a cliente opens its card; closing clears it", async () => {
    renderPage();
    const cards = await screen.findByTestId("clientes-cards");
    fireEvent.click(within(cards).getByRole("button", { name: "Abrir Oficina Lua" }));
    expect(await screen.findByTestId("card-stub")).toHaveTextContent("card de c2");
    fireEvent.click(screen.getByRole("button", { name: "fechar card" }));
    await waitFor(() => expect(screen.queryByTestId("card-stub")).not.toBeInTheDocument());
  });

  it("?id= deep link opens the card directly", async () => {
    renderPage("/clientes?id=c1");
    expect(await screen.findByTestId("card-stub")).toHaveTextContent("card de c1");
  });

  it("filters by status through the server", async () => {
    renderPage();
    await screen.findByTestId("clientes-cards");
    fireEvent.change(screen.getByLabelText("Filtrar por status"), { target: { value: "prospect" } });
    await waitFor(() => expect(api.get).toHaveBeenCalledWith("/api/clientes", { status: "prospect" }));
  });

  it("empty state (not loading) offers to add the first cliente", async () => {
    api.get.mockResolvedValue({ itens: [], total: 0 });
    renderPage();
    expect(await screen.findByText(/Nenhum cliente ainda/)).toBeInTheDocument();
  });

  it("shows the server's error instead of an empty list", async () => {
    api.get.mockRejectedValue(new Error("banco indisponível"));
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("banco indisponível");
    expect(screen.queryByText(/Nenhum cliente ainda/)).not.toBeInTheDocument();
  });

  it("Novo cliente creates it and opens its card", async () => {
    renderPage();
    await screen.findByTestId("clientes-cards");
    fireEvent.click(screen.getByTestId("clientes-novo"));
    const sheet = await screen.findByTestId("novo-cliente-sheet");
    fireEvent.change(within(sheet).getByLabelText("Nome"), { target: { value: "Nova Loja" } });
    fireEvent.click(within(sheet).getByRole("button", { name: "Adicionar" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/api/clientes", expect.objectContaining({ nome: "Nova Loja" })));
    expect(await screen.findByTestId("card-stub")).toHaveTextContent("card de c9");
  });
});
