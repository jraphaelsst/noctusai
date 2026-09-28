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

const { api, mockUser } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn(), upload: vi.fn() },
  mockUser: { current: { id: "usuario-1", user_metadata: { org_role: "admin" } as Record<string, unknown> } },
}));
vi.mock("@noctusai/seed/infra", () => ({ api, useAuthStore: () => ({ user: mockUser.current }) }));

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
  mockUser.current = { id: "usuario-1", user_metadata: { org_role: "admin" } };
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

describe("Custos — write controls are admin-only (leftovers item 8/17)", () => {
  it("a non-admin sees the custo/hora table read-only: no forms, no edit/remove/activate, no usuário select", async () => {
    mockUser.current = { id: "u", user_metadata: { org_role: "member" } };
    renderPage();
    await screen.findByText("Designer");
    await screen.findByText("Ana");

    expect(screen.queryByLabelText("Nome da função")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Adicionar função" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Nome")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Adicionar profissional" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Editar Designer" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remover Designer" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Editar Ana" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remover Ana" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Desativar|Ativar/ })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Usuário de Ana")).not.toBeInTheDocument();
  });

  it("an admin sees every write control", async () => {
    renderPage();
    await screen.findByLabelText("Nome da função");
    expect(screen.getByRole("button", { name: "Adicionar função" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Adicionar profissional" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Editar Ana" })).toBeInTheDocument();
    expect(screen.getByLabelText("Usuário de Ana")).toBeInTheDocument();
  });

  it("shows the server's real message on a duplicate função name, never a generic guess", async () => {
    const { ApiError } = await import("@noctusai/lib");
    api.post.mockImplementation(async (path: string) => {
      if (path === "/api/custos/funcoes") {
        throw new ApiError(409, "Já existe uma função com esse nome.", {
          detail: "Já existe uma função com esse nome.", code: "funcao_duplicada",
        });
      }
      throw new Error(`POST inesperado ${path}`);
    });
    renderPage();
    fireEvent.change(await screen.findByLabelText("Nome da função"), { target: { value: "Designer" } });
    fireEvent.click(screen.getByRole("button", { name: "Adicionar função" }));
    // describeError surfaces the server's real `detail` — never the raw
    // "[409] " prefix, never a generic guess.
    expect(await screen.findByText("Já existe uma função com esse nome.")).toBeInTheDocument();
  });
});
