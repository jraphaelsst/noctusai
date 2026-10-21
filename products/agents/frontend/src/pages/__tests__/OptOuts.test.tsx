/** OptOuts page -- loading / empty / error / success, the failed-notification state and the admin retry. Synthetic data. */
import React from "react";
import { MemoryRouter } from "react-router-dom";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockLista = vi.fn();
const mockReenviar = vi.fn();
const mockAdmin = vi.fn();
vi.mock("@/hooks/useOptOuts", () => ({
  useOptOuts: () => mockLista(),
  useReenviarNotificacao: () => ({ mutateAsync: mockReenviar, isPending: false }),
}));
vi.mock("@/hooks/useIsAdmin", () => ({ useIsAdmin: () => mockAdmin() }));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

const BASE = {
  id: "ev-1", lead_ref: "ref-1", lead_nome: "Fulano Sintético", lead_telefone: "+5511900000000", thread_id: "t1",
  agent_id: "a1", agent_key: "agente-x", agent_nome: "Agente X", ator_user_id: null, origem: "agente",
  motivo: "O lead pediu para parar", mensagem_lead: "pare de me escrever", em: "2026-10-20T14:30:00Z",
  participantes_encerrados: 2, notificacao_status: "enviada", notificacao_erro: null, notificado_em: "2026-10-20T14:31:00Z",
};
const FALHOU = { ...BASE, id: "ev-2", origem: "operador", agent_nome: null, notificacao_status: "falhou", notificacao_erro: "SemDestinatarios: sem admin", notificado_em: null };

function state(over: Record<string, unknown> = {}) {
  return {
    items: [BASE], showSkeleton: false, isRefreshing: false, isFetchingMore: false, hasMore: false, fetchMore: vi.fn(),
    isError: false, error: null, refetch: vi.fn(), ...over,
  };
}
async function renderPage(at = "/opt-outs") {
  const Page = (await import("@/pages/OptOuts")).default;
  render(React.createElement(MemoryRouter, { initialEntries: [at] }, React.createElement(Page)));
}

beforeEach(() => {
  vi.clearAllMocks();
  mockAdmin.mockReturnValue(true);
  mockLista.mockReturnValue(state());
});
afterEach(() => cleanup());

describe("OptOuts", () => {
  it("shows the skeleton while pending", async () => {
    mockLista.mockReturnValue(state({ items: undefined, showSkeleton: true }));
    await renderPage();
    expect(screen.getByTestId("optouts-skeleton")).toBeTruthy();
  });

  it("shows the empty state", async () => {
    mockLista.mockReturnValue(state({ items: [] }));
    await renderPage();
    expect(screen.getByTestId("optouts-empty")).toBeTruthy();
  });

  it("shows the error state with retry", async () => {
    const refetch = vi.fn();
    mockLista.mockReturnValue(state({ items: undefined, isError: true, error: new Error("falhou"), refetch }));
    await renderPage();
    expect(screen.getByTestId("optouts-error")).toBeTruthy();
    fireEvent.click(screen.getByText("Tentar novamente"));
    expect(refetch).toHaveBeenCalled();
  });

  it("lists who / why / what the lead said / conversations ended / notification status", async () => {
    await renderPage();
    expect(screen.getByText("Fulano Sintético")).toBeTruthy();
    expect(screen.getByText("+5511900000000")).toBeTruthy();
    expect(screen.getByTestId("optout-quem-ev-1").textContent).toBe("Agente Agente X");
    expect(screen.getByTestId("optout-motivo-ev-1").textContent).toBe("O lead pediu para parar");
    expect(screen.getByTestId("optout-mensagem-ev-1").textContent).toContain("pare de me escrever");
    expect(screen.getByTestId("optout-encerradas-ev-1").textContent).toBe("2");
    expect(screen.getByTestId("optout-status-ev-1").textContent).toContain("Dono avisado");
    expect(screen.queryByTestId("optout-reenviar-ev-1")).toBeNull();
  });

  it("makes a failed notification prominent with the error and lets an admin resend it", async () => {
    mockLista.mockReturnValue(state({ items: [FALHOU] }));
    mockReenviar.mockResolvedValue({ ...FALHOU, notificacao_status: "enviada", notificacao_erro: null });
    await renderPage();
    expect(screen.getByTestId("optout-quem-ev-2").textContent).toBe("Operador");
    expect(screen.getByTestId("optout-status-ev-2").textContent).toContain("Aviso falhou");
    expect(screen.getByTestId("optout-erro-ev-2").textContent).toContain("SemDestinatarios: sem admin");
    fireEvent.click(screen.getByTestId("optout-reenviar-ev-2"));
    await waitFor(() => expect(mockReenviar).toHaveBeenCalledWith("ev-2"));
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
  });

  it("reports a resend that fails again", async () => {
    mockLista.mockReturnValue(state({ items: [FALHOU] }));
    mockReenviar.mockResolvedValue({ ...FALHOU, notificacao_erro: "ainda fora" });
    await renderPage();
    fireEvent.click(screen.getByTestId("optout-reenviar-ev-2"));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(expect.stringContaining("ainda fora")));
  });

  it("hides the resend button from a non-admin", async () => {
    mockAdmin.mockReturnValue(false);
    mockLista.mockReturnValue(state({ items: [FALHOU] }));
    await renderPage();
    expect(screen.getByTestId("optout-erro-ev-2")).toBeTruthy();
    expect(screen.queryByTestId("optout-reenviar-ev-2")).toBeNull();
  });

  it("highlights the record the notification linked to and pages with a cursor", async () => {
    const fetchMore = vi.fn();
    mockLista.mockReturnValue(state({ items: [BASE, FALHOU], hasMore: true, fetchMore }));
    await renderPage("/opt-outs?evento=ev-2");
    expect(screen.getByTestId("optout-ev-2").getAttribute("data-destaque")).toBe("true");
    expect(screen.getByTestId("optout-ev-1").getAttribute("data-destaque")).toBeNull();
    fireEvent.click(screen.getByTestId("optouts-mais"));
    expect(fetchMore).toHaveBeenCalled();
  });
});
