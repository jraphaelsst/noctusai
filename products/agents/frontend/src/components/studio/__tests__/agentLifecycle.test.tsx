import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@noctusai/lib";

const post = vi.fn();
const del = vi.fn();
vi.mock("@/lib/api", () => ({ api: { post: (...a: unknown[]) => post(...a), delete: (...a: unknown[]) => del(...a) } }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
const navigate = vi.fn();
vi.mock("react-router-dom", async (orig) => ({ ...(await orig<typeof import("react-router-dom")>()), useNavigate: () => navigate }));

import { CriarAgentePlataformaDialog } from "../CriarAgentePlataformaDialog";
import { ExcluirAgenteDialog } from "../ExcluirAgenteDialog";
import { studioKeys } from "@/hooks/studio/keys";

function setup(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const spy = vi.spyOn(qc, "invalidateQueries");
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
  return { qc, spy };
}

beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

describe("CriarAgentePlataformaDialog", () => {
  it("creates by key, refreshes the list and navigates to the new empty agent", async () => {
    post.mockResolvedValue({ id: "1", key: "julia", org_id: "o", definition_scope: "plataforma", conteudo_modo: "linhas" });
    const onClose = vi.fn();
    const { spy } = setup(<CriarAgentePlataformaDialog onClose={onClose} />);
    expect((screen.getByTestId("criar-agente-submit") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByTestId("criar-agente-key"), { target: { value: "Julia" } });
    fireEvent.click(screen.getByTestId("criar-agente-submit"));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/studio/plataforma/agents", { key: "julia" }));
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/studio/julia"));
    expect(spy).toHaveBeenCalledWith({ queryKey: studioKeys.list() });
  });

  it("surfaces 422 chave_nao_registrada", async () => {
    post.mockRejectedValue(new ApiError(422, "Chave não registrada.", { detail: "Chave não registrada.", code: "chave_nao_registrada" }));
    setup(<CriarAgentePlataformaDialog onClose={vi.fn()} />);
    fireEvent.change(screen.getByTestId("criar-agente-key"), { target: { value: "xyz" } });
    fireEvent.click(screen.getByTestId("criar-agente-submit"));
    expect((await screen.findByTestId("criar-agente-erro")).textContent).toMatch(/Chave não registrada/);
    expect(navigate).not.toHaveBeenCalled();
  });
});

describe("ExcluirAgenteDialog", () => {
  it("gates the delete on typing the key, then deletes and invalidates the list", async () => {
    del.mockResolvedValue(null);
    const onClose = vi.fn();
    const { spy } = setup(<ExcluirAgenteDialog agentKey="julia" nome="Julia" onClose={onClose} />);
    const btn = screen.getByTestId("excluir-agente-confirm") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    fireEvent.change(screen.getByTestId("excluir-agente-key"), { target: { value: "juli" } });
    expect(btn.disabled).toBe(true);
    fireEvent.change(screen.getByTestId("excluir-agente-key"), { target: { value: "julia" } });
    expect(btn.disabled).toBe(false);
    fireEvent.click(btn);
    await waitFor(() => expect(del).toHaveBeenCalledWith("/api/studio/agents/julia"));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(spy).toHaveBeenCalledWith({ queryKey: studioKeys.list() });
  });

  it("shows the server's 409 reason plus a short hint", async () => {
    del.mockRejectedValue(
      new ApiError(409, "Erro HTTP 409", { code: "ativo", message: "O agente está ativo.", detail: "O agente está ativo." }),
    );
    const onClose = vi.fn();
    setup(<ExcluirAgenteDialog agentKey="julia" nome="Julia" onClose={onClose} />);
    fireEvent.change(screen.getByTestId("excluir-agente-key"), { target: { value: "julia" } });
    fireEvent.click(screen.getByTestId("excluir-agente-confirm"));
    expect((await screen.findByTestId("excluir-agente-erro")).textContent).toMatch(/O agente está ativo\./);
    expect(screen.getByTestId("excluir-agente-dica").textContent).toBe("Desligue o agente antes de excluir.");
    expect(onClose).not.toHaveBeenCalled();
  });
});
