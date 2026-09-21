/**
 * Interessados — `/interessados` (internal, admin). List + delete-with-
 * confirm over `GET`/`DELETE /api/interessados` (`projects/interessados-
 * CONTRACT.md`).
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockGet = vi.fn();
const mockDelete = vi.fn();

vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: mockDelete },
  createInteressado: vi.fn(),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function renderPage(ui: React.ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const CONTACT = {
  id: "c1",
  nome: "Maria Silva",
  whatsapp: "+5511987654321",
  email: "maria@exemplo.com",
  origem: "/como-funciona",
  consentimento_versao: "v1-2026-09",
  consentimento_em: "2026-09-01T00:00:00Z",
  criado_em: "2026-09-01T00:00:00Z",
};

beforeEach(() => vi.clearAllMocks());

describe("Interessados", () => {
  it("shows the empty state when there are no signups", async () => {
    mockGet.mockResolvedValue({ items: [], total: 0 });
    const { default: Interessados } = await import("../Interessados");
    renderPage(<Interessados />);

    await waitFor(() => expect(screen.getByText("Nenhum interessado cadastrado ainda.")).toBeInTheDocument());
    expect(mockGet).toHaveBeenCalledWith("/api/interessados", { limit: 50, offset: 0 });
  });

  it("lists signups from GET /api/interessados", async () => {
    mockGet.mockResolvedValue({ items: [CONTACT], total: 1 });
    const { default: Interessados } = await import("../Interessados");
    renderPage(<Interessados />);

    await waitFor(() => expect(screen.getByText("Maria Silva")).toBeInTheDocument());
    expect(screen.getByText(/maria@exemplo\.com/)).toBeInTheDocument();
    expect(screen.getByText("/como-funciona")).toBeInTheDocument();
  });

  it("shows the backend's error message when the list fails", async () => {
    mockGet.mockRejectedValue(new Error("boom"));
    const { default: Interessados } = await import("../Interessados");
    renderPage(<Interessados />);

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("boom"));
  });

  it("deletes a signup after the confirm dialog", async () => {
    mockGet.mockResolvedValue({ items: [CONTACT], total: 1 });
    mockDelete.mockResolvedValue(undefined);
    const { default: Interessados } = await import("../Interessados");
    renderPage(<Interessados />);

    await waitFor(() => expect(screen.getByText("Maria Silva")).toBeInTheDocument());

    fireEvent.click(screen.getByTestId("button-delete-c1"));
    expect(screen.getByText("Remover interessado")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("button-confirm-delete"));
    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith("/api/interessados/c1"));
  });

  it("cancelling the confirm dialog does not delete", async () => {
    mockGet.mockResolvedValue({ items: [CONTACT], total: 1 });
    const { default: Interessados } = await import("../Interessados");
    renderPage(<Interessados />);

    await waitFor(() => expect(screen.getByText("Maria Silva")).toBeInTheDocument());

    fireEvent.click(screen.getByTestId("button-delete-c1"));
    fireEvent.click(screen.getByText("Cancelar"));

    expect(screen.queryByText("Remover interessado")).not.toBeInTheDocument();
    expect(mockDelete).not.toHaveBeenCalled();
  });
});
