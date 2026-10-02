import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { screen, waitFor, act } from "@testing-library/react";
import "@testing-library/jest-dom";
import { ApiError } from "@noctusai/lib";
import { apiMock, renderWithProviders } from "@/test-utils";

vi.mock("@noctusai/seed/infra", () => ({ api: apiMock }));

import Obrigado from "../Obrigado";

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.useRealTimers());

describe("Obrigado", () => {
  it("pago: download button + masked e-mail", async () => {
    apiMock.get.mockResolvedValue({ status: "pago", produto: "Kit", email_mascarado: "j***@gmail.com", download_url: "/api/public/download/tok" });
    renderWithProviders(<Obrigado />, "/obrigado?pedido=tok");
    const btn = await screen.findByRole("link", { name: "Baixar meu kit" });
    expect(btn.getAttribute("href")).toContain("/api/public/download/tok");
    expect(screen.getByText(/j\*\*\*@gmail\.com/)).toBeInTheDocument();
    expect(apiMock.get).toHaveBeenCalledWith("/api/public/pedidos/tok");
  });

  it("pendente: waiting copy, polls again every 3 s, then gives up after 2 min", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    apiMock.get.mockResolvedValue({ status: "pendente", produto: "Kit", email_mascarado: "j***@gmail.com", download_url: null });
    renderWithProviders(<Obrigado />, "/obrigado?pedido=tok");
    expect((await screen.findAllByText(/Aguardando confirmação do pagamento/)).length).toBeGreaterThan(0);
    const first = apiMock.get.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(3100); });
    expect(apiMock.get.mock.calls.length).toBeGreaterThan(first);
    await act(async () => { await vi.advanceTimersByTimeAsync(120_000); });
    expect(await screen.findByText(/Assim que o pagamento for confirmado você recebe o link por e-mail/)).toBeInTheDocument();
    const settled = apiMock.get.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
    expect(apiMock.get.mock.calls.length).toBe(settled);
  });

  it("reembolsado state", async () => {
    apiMock.get.mockResolvedValue({ status: "reembolsado", produto: "Kit", email_mascarado: "j***@gmail.com", download_url: null });
    renderWithProviders(<Obrigado />, "/obrigado?pedido=tok");
    expect(await screen.findByText("Pedido reembolsado")).toBeInTheDocument();
    expect(screen.getByText(/acesso ao download foi encerrado/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Baixar meu kit" })).toBeNull();
  });

  it("not found (404) and missing token", async () => {
    apiMock.get.mockRejectedValue(new ApiError(404, "nf"));
    const { unmount } = renderWithProviders(<Obrigado />, "/obrigado?pedido=zzz");
    await waitFor(() => expect(screen.getByText("Pedido não encontrado")).toBeInTheDocument());
    unmount();
    renderWithProviders(<Obrigado />, "/obrigado");
    expect(screen.getByText("Pedido não encontrado")).toBeInTheDocument();
  });
});
