/**
 * Financeiro render tests — community-m2-contract.md §Frontend, amendments
 * A16/P3.
 *
 * `mockGet` routes by path since the page fires both `/api/assinaturas`
 * AND `/api/pagamentos` unconditionally (both tabs' data is loaded
 * up-front so switching tabs is instant).
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ApiError } from "@noctusai/lib";

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

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function renderPage(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

const ASSINATURA_ADMIN = {
  id: "a-1",
  membro_id: "m-1",
  membro_nome: "Ana",
  plano_id: "p-1",
  plano_nome: "Círculo",
  gateway: "stripe",
  estado: "ativa",
  metodo: "cartao",
  ciclo: "mensal",
  assinatura_externa_id: "sub_123",
  iniciada_em: "2026-09-01T00:00:00+00:00",
  ativa_em: "2026-09-02T00:00:00+00:00",
  cancelada_em: null,
};

/** A moderador gets this same route with `assinatura_externa_id` ABSENT (P3). */
const ASSINATURA_MODERADOR = {
  id: "a-2",
  membro_id: "m-2",
  membro_nome: "Bia",
  plano_id: "p-1",
  plano_nome: "Círculo",
  gateway: "asaas",
  estado: "inadimplente",
  metodo: "pix",
  ciclo: "mensal",
  iniciada_em: "2026-09-01T00:00:00+00:00",
  ativa_em: null,
  cancelada_em: null,
};

beforeEach(() => vi.clearAllMocks());

describe("Financeiro — Assinaturas tab", () => {
  it("shows the loading skeleton, then renders subscription rows", async () => {
    mockGet.mockImplementation((path: string) => {
      if (path === "/api/pagamentos") return Promise.resolve({ items: [], total: 0 });
      return Promise.resolve({ items: [ASSINATURA_ADMIN], total: 1 });
    });
    const { default: Financeiro } = await import("../Financeiro");
    renderPage(<Financeiro />);

    await waitFor(() => expect(screen.getByTestId("assinatura-row-a-1")).toBeInTheDocument());
    expect(screen.getByTestId("assinatura-row-a-1")).toHaveTextContent("Ana");
    expect(screen.getByTestId("assinatura-row-a-1")).toHaveTextContent("Círculo");
  });

  it("shows the empty-state copy explaining nothing appears until the first checkout", async () => {
    mockGet.mockResolvedValue({ items: [], total: 0 });
    const { default: Financeiro } = await import("../Financeiro");
    renderPage(<Financeiro />);

    await waitFor(() =>
      expect(
        screen.getByText(/Assinaturas aparecem aqui após o primeiro checkout/),
      ).toBeInTheDocument(),
    );
  });

  it("P3 — renders a moderador-shaped row (no assinatura_externa_id) without crashing", async () => {
    mockGet.mockImplementation((path: string) => {
      if (path === "/api/pagamentos") {
        return Promise.reject(new ApiError(403, "Apenas administradores podem ver os pagamentos."));
      }
      return Promise.resolve({ items: [ASSINATURA_MODERADOR], total: 1 });
    });
    const { default: Financeiro } = await import("../Financeiro");
    renderPage(<Financeiro />);

    await waitFor(() => expect(screen.getByTestId("assinatura-row-a-2")).toBeInTheDocument());
    expect(screen.getByTestId("assinatura-row-a-2")).toHaveTextContent("Bia");
    expect(screen.getByTestId("assinatura-row-a-2")).toHaveTextContent("Inadimplente");
  });

  it("cancels a subscription with the required motivo", async () => {
    mockGet.mockImplementation((path: string) => {
      if (path === "/api/pagamentos") return Promise.resolve({ items: [], total: 0 });
      return Promise.resolve({ items: [ASSINATURA_ADMIN], total: 1 });
    });
    mockPost.mockResolvedValue({ ...ASSINATURA_ADMIN, estado: "cancelada" });
    const { default: Financeiro } = await import("../Financeiro");
    renderPage(<Financeiro />);

    await waitFor(() => expect(screen.getByTestId("assinatura-cancelar-a-1")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("assinatura-cancelar-a-1"));
    fireEvent.change(screen.getByLabelText(/Motivo/), { target: { value: "Solicitado pelo membro" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirmar cancelamento" }));

    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith("/api/assinaturas/a-1/cancelar", { motivo: "Solicitado pelo membro" }),
    );
  });
});

describe("Financeiro — Pagamentos tab (A16/P3 admin-only)", () => {
  it("renders the backend's strict-403 detail for a moderador, not a crash", async () => {
    mockGet.mockImplementation((path: string) => {
      if (path === "/api/pagamentos") {
        return Promise.reject(new ApiError(403, "Apenas administradores podem ver os pagamentos."));
      }
      return Promise.resolve({ items: [], total: 0 });
    });
    const { default: Financeiro } = await import("../Financeiro");
    renderPage(<Financeiro />);

    fireEvent.click(screen.getByRole("button", { name: "Pagamentos" }));
    await waitFor(() =>
      expect(screen.getByText("Apenas administradores podem ver os pagamentos.")).toBeInTheDocument(),
    );
  });

  it("renders payment rows with BRL-formatted amounts for an admin", async () => {
    mockGet.mockImplementation((path: string) => {
      if (path === "/api/pagamentos") {
        return Promise.resolve({
          items: [
            {
              id: "pg-1",
              membro_id: "m-1",
              membro_nome: "Ana",
              assinatura_id: "a-1",
              gateway: "stripe",
              cobranca_externa_id: "ch_123",
              valor_centavos: 9900,
              metodo: "cartao",
              estado: "pago",
              pago_em: "2026-09-16T20:00:00+00:00",
              vencimento: null,
              url_fatura: "https://stripe.example/invoice/123",
              pix_payload: null,
              pix_imagem_base64: null,
              created_at: "2026-09-16T20:00:00+00:00",
            },
          ],
          total: 1,
        });
      }
      return Promise.resolve({ items: [], total: 0 });
    });
    const { default: Financeiro } = await import("../Financeiro");
    renderPage(<Financeiro />);

    fireEvent.click(screen.getByRole("button", { name: "Pagamentos" }));
    await waitFor(() => expect(screen.getByTestId("pagamento-row-pg-1")).toBeInTheDocument());
    expect(screen.getByTestId("pagamento-row-pg-1")).toHaveTextContent("R$");
    expect(screen.getByText("Ver fatura")).toBeInTheDocument();
  });
});
