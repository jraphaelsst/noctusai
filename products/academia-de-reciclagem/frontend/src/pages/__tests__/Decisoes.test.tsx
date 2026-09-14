/**
 * Decisoes — page-level render test for the supersede flow.
 *
 * Mocks `@/lib/api` only. Opens the detail dialog, triggers "Substituir",
 * submits the supersede form, and asserts the result panel shows BOTH the
 * new and the replaced decision (contract §B.2: `POST
 * /api/decisions/{codigo}/supersede` → `{nova, substituida}`).
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import { MemoryRouter } from "react-router-dom";
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
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

const D10 = {
  codigo: "D-10",
  titulo: "Usar Postgres",
  contexto: "Precisamos de um banco relacional",
  decisao: "Adotar Postgres como banco principal",
  motivo: "Já usado no resto da plataforma",
  alternativas_rejeitadas: null,
  data: "2026-08-01",
  estado: "vigente",
  substitui: null,
  superseded_by: null,
  relacionadas: [],
};

beforeEach(() => {
  vi.clearAllMocks();
  mockGet.mockImplementation((path: string) => {
    if (path === "/api/decisions") return Promise.resolve({ items: [D10], total: 1 });
    if (path === "/api/decisions/D-10") return Promise.resolve(D10);
    return Promise.reject(new Error(`unexpected GET ${path}`));
  });
});

describe("Decisoes — supersede flow", () => {
  it("shows both the new and the replaced decision after supersede", async () => {
    const nova = { ...D10, codigo: "D-21", titulo: "Usar Postgres 16", substitui: "D-10" };
    const substituida = { ...D10, estado: "superseded", superseded_by: "D-21" };
    mockPost.mockResolvedValue({ nova, substituida });

    const { default: Decisoes } = await import("../Decisoes");
    renderPage(<Decisoes />);

    await waitFor(() => expect(screen.getByText("Usar Postgres")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Usar Postgres"));

    await waitFor(() => expect(screen.getByText("Substituir")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Substituir"));

    const dialogTitulo = await screen.findByLabelText(/título/i);
    fireEvent.change(dialogTitulo, { target: { value: "Usar Postgres 16" } });
    fireEvent.change(screen.getByLabelText(/^decisão/i), {
      target: { value: "Migrar para Postgres 16" },
    });
    fireEvent.change(screen.getByLabelText(/^motivo/i), {
      target: { value: "Suporte a recursos novos" },
    });

    const substituirButtons = screen.getAllByRole("button", { name: "Substituir" });
    fireEvent.click(substituirButtons[substituirButtons.length - 1]);

    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith(
        "/api/decisions/D-10/supersede",
        expect.objectContaining({ titulo: "Usar Postgres 16" }),
      ),
    );

    expect(await screen.findByText("Usar Postgres 16")).toBeInTheDocument();
    expect(screen.getByText(/Substitui: D-10/)).toBeInTheDocument();
    expect(screen.getByText(/Substituída por: D-21/)).toBeInTheDocument();
  });
});
