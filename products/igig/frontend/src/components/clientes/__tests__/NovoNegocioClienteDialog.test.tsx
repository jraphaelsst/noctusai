/**
 * "Novo negócio" from a cliente's own card (comercial achado 12 —
 * upsell/renewal): posts `cliente_id` alongside a lead row built from that
 * cliente's contact data, and hands the new negócio's id to the caller
 * (router-agnostic — no `<Router>` context needed here).
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

import { NovoNegocioClienteDialog } from "../NovoNegocioClienteDialog";
import type { Cliente } from "@/hooks/useClientes";

const CLIENTE: Cliente = {
  id: "c1", org_id: "org", nome: "Padaria Sol", nicho: "Alimentação", email: "sol@padaria.com",
  telefone: "11999990000", status: "ativo", origem: null, observacoes: null,
  created_at: "2026-09-01T10:00:00Z", updated_at: null,
};

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

describe("NovoNegocioClienteDialog", () => {
  it("renders nothing without a cliente", () => {
    wrap(<NovoNegocioClienteDialog cliente={null} onClose={vi.fn()} />);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("posts cliente_id + a lead built from the cliente, then hands the id to onCriado", async () => {
    api.post.mockResolvedValue({ data: { id: "n9", titulo: "Padaria Sol" } });
    const onCriado = vi.fn();
    wrap(<NovoNegocioClienteDialog cliente={CLIENTE} onClose={vi.fn()} onCriado={onCriado} />);

    fireEvent.change(screen.getByLabelText("Título (opcional)"), { target: { value: "Upsell" } });
    fireEvent.click(screen.getByRole("button", { name: "Criar negócio" }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith("/api/comercial/negocios", {
        lead: { nome: "Padaria Sol", email: "sol@padaria.com", telefone: "11999990000" },
        cliente_id: "c1",
        titulo: "Upsell",
        valor_estimado: undefined,
      }),
    );
    await waitFor(() => expect(onCriado).toHaveBeenCalledWith("n9"));
  });
});
