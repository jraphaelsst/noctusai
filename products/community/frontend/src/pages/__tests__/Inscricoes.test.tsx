/**
 * Inscrições page render tests — community-m1-contract.md §Frontend.
 *
 * Covers the applications queue's loading/empty/error/success states and
 * the `resumo` tab counts. The questions editor (ResourceManager) is
 * exercised separately by the organ's own colocated test
 * (`seed/lib/frontend/src/components/ResourceManager.test.tsx`); here we
 * only assert the toggle reveals it.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();
const mockDelete = vi.fn();

vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: mockPost, put: vi.fn(), patch: mockPatch, delete: mockDelete },
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

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function renderPage(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

function neverResolves() {
  return new Promise(() => {});
}

const RESUMO = { pendente: 2, aprovada: 5, rejeitada: 1 };

const APLICACAO = {
  id: "a-1",
  nome: "Beatriz",
  email: "bea@x.com",
  telefone: null,
  respostas: { "q-1": "Porque sim" },
  status: "pendente",
  motivo: null,
  revisado_em: null,
  membro_id: null,
  created_at: "2026-09-16T20:00:00+00:00",
};

beforeEach(() => vi.clearAllMocks());

describe("Inscrições — loading vs empty vs data", () => {
  it("shows the skeleton on first load", async () => {
    mockGet.mockReturnValue(neverResolves());
    const { default: Inscricoes } = await import("../Inscricoes");
    const { getByTestId } = renderPage(<Inscricoes />);

    await waitFor(() => expect(getByTestId("aplicacoes-skeleton")).toBeInTheDocument());
  });

  it("renders the empty state once settled with no pending applications", async () => {
    mockGet.mockResolvedValue({ items: [], total: 0, resumo: RESUMO });
    const { default: Inscricoes } = await import("../Inscricoes");
    renderPage(<Inscricoes />);

    await waitFor(() => expect(screen.getByText("Nenhuma inscrição encontrada.")).toBeInTheDocument());
  });

  it("renders applications with resumo tab counts and answers resolved to question labels", async () => {
    mockGet.mockImplementation((path: string) => {
      if (path === "/api/aplicacoes/perguntas") {
        return Promise.resolve({
          items: [{ id: "q-1", pergunta: "Por que quer entrar?", tipo: "texto_longo", opcoes: [], obrigatoria: true, ordem: 0, ativa: true }],
          total: 1,
        });
      }
      return Promise.resolve({ items: [APLICACAO], total: 1, resumo: RESUMO });
    });
    const { default: Inscricoes } = await import("../Inscricoes");
    renderPage(<Inscricoes />);

    await waitFor(() => expect(screen.getByText("Beatriz")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Pendentes (2)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Aprovadas (5)" })).toBeInTheDocument();

    fireEvent.click(screen.getByText("Ver respostas"));
    await waitFor(() => expect(screen.getByText(/Por que quer entrar\?/)).toBeInTheDocument());
  });

  it("reveals the questions editor on toggle", async () => {
    mockGet.mockResolvedValue({ items: [], total: 0, resumo: RESUMO });
    const { default: Inscricoes } = await import("../Inscricoes");
    renderPage(<Inscricoes />);

    await waitFor(() => expect(screen.getByTestId("toggle-perguntas-editor")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("toggle-perguntas-editor"));
    await waitFor(() =>
      expect(screen.getByText("O que os candidatos respondem ao se inscrever.")).toBeInTheDocument(),
    );
  });
});

describe("Inscrições — error → contract detail text", () => {
  it("shows the backend's detail text for a failed fetch", async () => {
    const { ApiError } = await import("@noctusai/lib");
    mockGet.mockRejectedValue(new ApiError(500, "Erro interno."));
    const { default: Inscricoes } = await import("../Inscricoes");
    renderPage(<Inscricoes />);

    await waitFor(() => expect(screen.getByText("Erro interno.")).toBeInTheDocument());
  });
});
