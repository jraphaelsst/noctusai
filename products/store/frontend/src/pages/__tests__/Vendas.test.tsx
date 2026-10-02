import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import { ApiError } from "@noctusai/lib";
import { apiMock, renderWithProviders } from "@/test-utils";

vi.mock("@noctusai/seed/infra", () => ({ api: apiMock }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import Vendas from "../Vendas";

const PEDIDO = {
  id: "p1", nome: "Maria Silva", email: "maria@exemplo.com", valor_cents: 4700, status: "pago",
  created_at: "2026-10-01T10:00:00Z", email_enviado_em: "2026-10-01T10:01:00Z", downloads: 2,
};
beforeEach(() => vi.clearAllMocks());

describe("Vendas", () => {
  it("lists orders and resends the e-mail", async () => {
    apiMock.get.mockResolvedValue({ items: [PEDIDO] });
    apiMock.post.mockResolvedValue({});
    renderWithProviders(<Vendas />);
    expect(await screen.findByText("Maria Silva")).toBeInTheDocument();
    expect(screen.getByText("R$ 47,00")).toBeInTheDocument();
    expect(screen.getByText("Pago")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reenviar e-mail" }));
    await waitFor(() => expect(apiMock.post).toHaveBeenCalledWith("/api/admin/pedidos/p1/reenviar"));
  });

  it("empty state", async () => {
    apiMock.get.mockResolvedValue([]);
    renderWithProviders(<Vendas />);
    expect(await screen.findByText("Nenhuma venda ainda.")).toBeInTheDocument();
  });

  it("403 → Sem acesso", async () => {
    apiMock.get.mockRejectedValue(new ApiError(403, "no"));
    renderWithProviders(<Vendas />);
    expect(await screen.findByText("Sem acesso")).toBeInTheDocument();
    expect(screen.queryByText("Vendas")).toBeNull();
  });
});
