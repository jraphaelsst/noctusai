/**
 * MarcasSubpage — a cliente carries N marcas (roadmap R9): chips per marca,
 * the selected marca's panel, "Nova marca" (POST), remove (DELETE, confirmed),
 * and the load-error state. Real hooks over a mocked `api`.
 */
/// <reference types="@testing-library/jest-dom" />
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import "@testing-library/jest-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const { api } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn(), upload: vi.fn() },
}));
vi.mock("@noctusai/seed/infra", () => ({ api }));
// The vault has its own colocated test.
vi.mock("../CofreAcessos", () => ({ CofreAcessos: () => null }));

import { MarcasSubpage } from "../MarcasSubpage";

const base = {
  org_id: "org", cliente_id: "c1", logo_url: null, paleta: [], tom_de_voz: null, termos_proibidos: null,
  nivel_formalidade: null, linhas_editoriais: [], personas: [],
};
let marcas: Array<Record<string, unknown>> = [];

function renderSub() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MarcasSubpage clienteId="c1" clienteNome="Padaria Sol" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  marcas = [
    { ...base, id: "m1", nome: "Sol Pães", tom_de_voz: "caloroso" },
    { ...base, id: "m2", nome: "Sol Café" },
  ];
  api.get.mockImplementation(async (path: string, params?: Record<string, unknown>) => {
    if (path === "/api/marcas" && params?.cliente_id === "c1") return marcas;
    throw new Error(`GET inesperado ${path}`);
  });
  api.post.mockImplementation(async (_p: string, body: Record<string, unknown>) => {
    const nova = { ...base, id: "m3", nome: body.nome };
    marcas = [...marcas, nova];
    return nova;
  });
  api.delete.mockImplementation(async (path: string) => {
    marcas = marcas.filter((m) => `/api/marcas/${m.id}` !== path);
    return { ok: true };
  });
});
afterEach(cleanup);

describe("MarcasSubpage", () => {
  it("shows one chip per marca and the first marca's panel", async () => {
    renderSub();
    const tabs = await screen.findAllByRole("tab");
    expect(tabs.map((t) => t.textContent)).toEqual(["Sol Pães", "Sol Café"]);
    expect(screen.getByTestId("marca-panel-m1")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Sol Café" }));
    expect(await screen.findByTestId("marca-panel-m2")).toBeInTheDocument();
  });

  it("creates a new marca for the cliente and selects it", async () => {
    renderSub();
    fireEvent.click(await screen.findByRole("button", { name: /Nova marca/ }));
    fireEvent.change(screen.getByLabelText("Nome da nova marca"), { target: { value: "Sol Doces" } });
    fireEvent.click(screen.getByRole("button", { name: "Criar" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/api/marcas", { cliente_id: "c1", nome: "Sol Doces" }));
    expect(await screen.findByTestId("marca-panel-m3")).toBeInTheDocument();
  });

  it("removes a marca only after the confirmation", async () => {
    renderSub();
    fireEvent.click(await screen.findByRole("button", { name: "Remover marca Sol Pães" }));
    expect(api.delete).not.toHaveBeenCalled();
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Remover" }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/api/marcas/m1"));
    await waitFor(() => expect(screen.queryByRole("tab", { name: "Sol Pães" })).not.toBeInTheDocument());
  });

  it("offers to create the first marca when the cliente has none", async () => {
    marcas = [];
    renderSub();
    expect(await screen.findByText("Nenhuma marca cadastrada para este cliente.")).toBeInTheDocument();
  });

  it("shows the server's error instead of an empty state", async () => {
    api.get.mockRejectedValue(new Error("banco indisponível"));
    renderSub();
    expect(await screen.findByRole("alert")).toHaveTextContent("banco indisponível");
    expect(screen.queryByText("Nenhuma marca cadastrada para este cliente.")).not.toBeInTheDocument();
  });
});
