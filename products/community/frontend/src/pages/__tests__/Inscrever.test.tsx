/**
 * Inscrever (public application form) render tests —
 * community-m1-contract.md §Frontend.
 *
 * This page is mounted as a `publicRoute` — no auth, no Layout. These tests
 * render it standalone (no AuthProvider needed) proving loading/empty/
 * error/success plus the 409 "already applied" contract message.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockGet = vi.fn();
const mockPost = vi.fn();

vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: mockPost, put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

vi.mock("@noctusai/seed/infra", () => {
  const noop = () => {};
  const api = { get: noop, post: noop, patch: noop, delete: noop };
  return {
    api,
    coreApi: api,
    supabase: {},
    appConfig: {},
    useAuthStore: () => ({ user: null }),
    AuthProvider: ({ children }: { children?: unknown }) => children,
    NotificationBell: () => null,
    useNotificacoes: () => ({ data: [] }),
    useContagemNaoLidas: () => ({ data: 0 }),
    useMarcarComoLida: () => ({ mutate: noop }),
    useMarcarTodasComoLidas: () => ({ mutate: noop }),
    default: { api },
  };
});

function renderPage(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

function neverResolves() {
  return new Promise(() => {});
}

const PERGUNTA = {
  id: "q-1",
  pergunta: "Por que quer entrar?",
  tipo: "texto",
  opcoes: [],
  obrigatoria: true,
  ordem: 0,
  ativa: true,
};

beforeEach(() => vi.clearAllMocks());

describe("Inscrever — loading vs empty vs data", () => {
  it("shows the skeleton on first load", async () => {
    mockGet.mockReturnValue(neverResolves());
    const { default: Inscrever } = await import("../Inscrever");
    const { getByTestId } = renderPage(<Inscrever />);

    await waitFor(() => expect(getByTestId("inscrever-skeleton")).toBeInTheDocument());
  });

  it("shows a friendly message when the formulário has no active questions", async () => {
    mockGet.mockResolvedValue({ items: [], total: 0 });
    const { default: Inscrever } = await import("../Inscrever");
    renderPage(<Inscrever />);

    await waitFor(() =>
      expect(screen.getByText("O formulário de inscrição não está disponível no momento.")).toBeInTheDocument(),
    );
  });

  it("renders the public form and submits respostas keyed by pergunta_id", async () => {
    mockGet.mockResolvedValue({ items: [PERGUNTA], total: 1 });
    mockPost.mockResolvedValue({ id: "a-1", status: "pendente" });
    const { default: Inscrever } = await import("../Inscrever");
    renderPage(<Inscrever />);

    await waitFor(() => expect(screen.getByText(/Por que quer entrar\?/)).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/Nome/), { target: { value: "Beatriz" } });
    fireEvent.change(screen.getByLabelText(/E-mail/), { target: { value: "bea@x.com" } });
    fireEvent.change(screen.getByLabelText(/Por que quer entrar\?/), { target: { value: "Porque sim" } });
    fireEvent.click(screen.getByText("Enviar inscrição"));

    await waitFor(() => expect(screen.getByTestId("inscrever-success")).toBeInTheDocument());
    expect(mockPost).toHaveBeenCalledWith("/api/aplicacoes", {
      nome: "Beatriz",
      email: "bea@x.com",
      telefone: null,
      respostas: { "q-1": "Porque sim" },
    });
  });

  it("shows the contract's 409 duplicate-application message", async () => {
    mockGet.mockResolvedValue({ items: [PERGUNTA], total: 1 });
    const { ApiError } = await import("@noctusai/lib");
    mockPost.mockRejectedValue(
      new ApiError(409, "Já existe uma inscrição em análise para esse e-mail."),
    );
    const { default: Inscrever } = await import("../Inscrever");
    renderPage(<Inscrever />);

    await waitFor(() => expect(screen.getByText(/Por que quer entrar\?/)).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText(/Nome/), { target: { value: "Beatriz" } });
    fireEvent.change(screen.getByLabelText(/E-mail/), { target: { value: "bea@x.com" } });
    fireEvent.change(screen.getByLabelText(/Por que quer entrar\?/), { target: { value: "Porque sim" } });
    fireEvent.click(screen.getByText("Enviar inscrição"));

    await waitFor(() =>
      expect(screen.getByText("Já existe uma inscrição em análise para esse e-mail.")).toBeInTheDocument(),
    );
  });
});

describe("Inscrever — error state", () => {
  it("shows an error state when the formulário fails to load", async () => {
    const { ApiError } = await import("@noctusai/lib");
    mockGet.mockRejectedValue(new ApiError(500, "Erro interno."));
    const { default: Inscrever } = await import("../Inscrever");
    renderPage(<Inscrever />);

    await waitFor(() => expect(screen.getByText("Erro interno.")).toBeInTheDocument());
  });
});
