import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@noctusai/lib";

const post = vi.fn();
const get = vi.fn();
const del = vi.fn();
vi.mock("@/lib/api", () => ({ api: { get: (...a: unknown[]) => get(...a), post: (...a: unknown[]) => post(...a), delete: (...a: unknown[]) => del(...a) } }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
const navigate = vi.fn();
vi.mock("react-router-dom", async (orig) => ({ ...(await orig<typeof import("react-router-dom")>()), useNavigate: () => navigate }));

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

beforeEach(() => {
  vi.clearAllMocks();
  get.mockResolvedValue({ items: [] });
});
afterEach(cleanup);

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
