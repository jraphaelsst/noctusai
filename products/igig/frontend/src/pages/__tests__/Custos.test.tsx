/**
 * Custos — achado 13: editing a profissional's função/custo_hora_override
 * was impossible after creation (only usuário/ativo could change), and
 * removing a função/profissional had no confirmation.
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

import Custos from "../Custos";

const FUNCAO = { id: "f1", org_id: "o", nome: "Designer", custo_hora_padrao: 85 };
const PROF = {
  id: "p1", org_id: "o", nome: "Ana", funcao_id: "f1", custo_hora_override: null,
  usuario_id: null, ativo: true, custo_hora_efetivo: 85, custo_hora_indefinido: false,
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <Custos />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(window, "confirm").mockReturnValue(true);
  api.get.mockImplementation(async (path: string) => {
    if (path === "/api/custos/funcoes") return [FUNCAO];
    if (path === "/api/custos/profissionais") return [PROF];
    if (path === "/api/team") return { data: [] };
    throw new Error(`GET inesperado ${path}`);
  });
  api.patch.mockImplementation(async () => ({ ...PROF, custo_hora_override: 120 }));
  api.delete.mockImplementation(async () => ({ ok: true }));
});

afterEach(cleanup);

describe("Custos — profissional edit + delete confirmation", () => {
  it("edits a profissional's função/custo_hora_override (achado 13)", async () => {
    renderPage();
    const editar = await screen.findByRole("button", { name: "Editar Ana" });
    fireEvent.click(editar);

    // Two inputs share this placeholder: the "add profissional" form (always
    // rendered) and this row's edit form — the edit one is the LAST one.
    const todos = screen.getAllByPlaceholderText("herda da função");
    const overrideInput = todos[todos.length - 1];
    fireEvent.change(overrideInput, { target: { value: "120" } });
    fireEvent.click(screen.getByRole("button", { name: /Salvar/ }));

    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith(
        "/api/custos/profissionais/p1",
        expect.objectContaining({ nome: "Ana", funcao_id: "f1", custo_hora_override: 120 }),
      ),
    );
  });

  it("asks for confirmation before removing a função", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Remover Designer" }));
    expect(window.confirm).toHaveBeenCalled();
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/api/custos/funcoes/f1"));
  });

  it("asks for confirmation before removing a profissional", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Remover Ana" }));
    expect(window.confirm).toHaveBeenCalled();
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/api/custos/profissionais/p1"));
  });

  it("declining the confirmation does not delete", async () => {
    (window.confirm as ReturnType<typeof vi.fn>).mockReturnValueOnce(false);
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Remover Ana" }));
    expect(api.delete).not.toHaveBeenCalled();
  });
});
