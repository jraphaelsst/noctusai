/**
 * "Novo lead" — default "Novo contato" flow (regression) plus "Cliente
 * existente" (comercial achado 12 — upsell/renewal): searching, picking an
 * existing cliente, and submitting with `cliente_id` alongside a lead row
 * built from that cliente's own contact data.
 */
/// <reference types="@testing-library/jest-dom" />
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const { api } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn(), upload: vi.fn() },
}));
vi.mock("@noctusai/seed/infra", () => ({ api }));

import { NovoLeadDialog } from "../NovoLeadDialog";

const CLIENTE = {
  id: "c1", org_id: "org", nome: "Padaria Sol", nicho: "Alimentação", email: "sol@padaria.com",
  telefone: null, status: "ativo", origem: null, observacoes: null, created_at: "2026-09-01T10:00:00Z", updated_at: null,
};

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  api.get.mockImplementation(async (path: string) => {
    if (path === "/api/clientes") return { itens: [CLIENTE], total: 1 };
    throw new Error(`GET inesperado ${path}`);
  });
  api.post.mockResolvedValue({ data: { id: "n1", titulo: "Padaria Sol" } });
});
afterEach(cleanup);

describe("NovoLeadDialog", () => {
  it("Novo contato (default): posts a fresh lead, no cliente_id", async () => {
    wrap(<NovoLeadDialog open onClose={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Ana" } });
    fireEvent.click(screen.getByRole("button", { name: "Criar lead" }));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        "/api/comercial/negocios",
        expect.objectContaining({ lead: expect.objectContaining({ nome: "Ana" }) }),
      ),
    );
    expect(api.post.mock.calls[0][1]).not.toHaveProperty("cliente_id");
  });

  it("Cliente existente: searches, picks a cliente, and posts cliente_id + a lead built from it", async () => {
    wrap(<NovoLeadDialog open onClose={vi.fn()} />);
    fireEvent.click(screen.getByTestId("novo-lead-modo-cliente"));

    fireEvent.change(screen.getByLabelText("Buscar cliente"), { target: { value: "Padaria" } });
    await waitFor(() => expect(api.get).toHaveBeenCalledWith("/api/clientes", { busca: "Padaria", limit: "20" }));

    const opcao = await screen.findByText("Padaria Sol");
    fireEvent.click(opcao);

    // Selecting collapses the search into a chip with a "Trocar" affordance.
    expect(screen.getByRole("button", { name: "Trocar" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Criar negócio" }));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith("/api/comercial/negocios", {
        lead: { nome: "Padaria Sol", email: "sol@padaria.com", telefone: undefined },
        cliente_id: "c1",
        valor_estimado: undefined,
      }),
    );
  });

  it("Criar negócio stays disabled until a cliente is picked", () => {
    wrap(<NovoLeadDialog open onClose={vi.fn()} />);
    fireEvent.click(screen.getByTestId("novo-lead-modo-cliente"));
    expect(screen.getByRole("button", { name: "Criar negócio" })).toBeDisabled();
  });
});
