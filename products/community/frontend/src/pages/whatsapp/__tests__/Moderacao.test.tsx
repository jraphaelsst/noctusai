/** Moderação page render tests — list, resolve call, empty state, moderador access. */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockDelete = vi.fn();

vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: mockPost, put: vi.fn(), patch: vi.fn(), delete: mockDelete },
}));

const mockUseAuthStore = vi.fn(() => ({ user: null as unknown }));

vi.mock("@noctusai/seed/infra", () => {
  const noop = () => {};
  const api = { get: noop, post: noop, patch: noop, delete: noop };
  return {
    api,
    coreApi: api,
    supabase: {},
    appConfig: {},
    useAuthStore: () => mockUseAuthStore(),
    AuthProvider: ({ children }: { children?: unknown }) => children,
    NotificationBell: () => null,
    useNotificacoes: () => ({ data: [] }),
    useContagemNaoLidas: () => ({ data: 0 }),
    useMarcarComoLida: () => ({ mutate: noop }),
    useMarcarTodasComoLidas: () => ({ mutate: noop }),
    default: { api },
  };
});

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

function renderPage(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

const FLAG = {
  id: "f-1",
  mensagem_id: "m-1",
  grupo_id: "g-1",
  categoria: "spam",
  severidade: "alta",
  justificativa: "Divulgação de link suspeito",
  modelo: "gpt",
  prompt_versao: "v1",
  estado: "aberta",
  resolvido_por: null,
  resolvido_em: null,
  created_at: "2026-09-30T10:00:00+00:00",
};

function mockRoutes(flags: unknown = { items: [FLAG], total: 1 }) {
  mockGet.mockImplementation((path: string) => {
    if (path === "/api/whatsapp/sessao") return Promise.resolve({ estado: "WORKING", sessao: "default" });
    if (path === "/api/whatsapp/flags") return Promise.resolve(flags);
    if (path === "/api/whatsapp/grupos") {
      return Promise.resolve({ items: [{ id: "g-1", nome: "Comunidade Oficial", ativo: true }], total: 1 });
    }
    return Promise.reject(new Error(`unexpected GET ${path}`));
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseAuthStore.mockReturnValue({ user: { user_metadata: { org_role: "admin" } } });
});

describe("Moderacao", () => {
  it("renders the flag list with group name, category and reason", async () => {
    mockRoutes();
    const { default: Moderacao } = await import("../Moderacao");
    renderPage(<Moderacao />);
    await waitFor(() => expect(screen.getByTestId("flag-f-1")).toBeInTheDocument());
    const row = screen.getByTestId("flag-f-1");
    expect(row).toHaveTextContent("spam");
    expect(row).toHaveTextContent("Divulgação de link suspeito");
    await waitFor(() => expect(row).toHaveTextContent("Comunidade Oficial"));
    expect(mockGet).toHaveBeenCalledWith("/api/whatsapp/flags", expect.objectContaining({ estado: "aberta" }));
  });

  it("resolves a flag with the note, one human decision at a time", async () => {
    mockRoutes();
    mockPost.mockResolvedValue({ ...FLAG, estado: "resolvida" });
    const { default: Moderacao } = await import("../Moderacao");
    renderPage(<Moderacao />);
    await waitFor(() => expect(screen.getByTestId("flag-resolver-f-1")).toBeInTheDocument());
    fireEvent.change(screen.getByTestId("flag-nota-f-1"), { target: { value: "ok" } });
    fireEvent.click(screen.getByTestId("flag-resolver-f-1"));
    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith("/api/whatsapp/flags/f-1/resolver", { estado: "resolvida", nota: "ok" }),
    );
  });

  it("dismisses a flag without a note", async () => {
    mockRoutes();
    mockPost.mockResolvedValue({ ...FLAG, estado: "descartada" });
    const { default: Moderacao } = await import("../Moderacao");
    renderPage(<Moderacao />);
    await waitFor(() => expect(screen.getByTestId("flag-descartar-f-1")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("flag-descartar-f-1"));
    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith("/api/whatsapp/flags/f-1/resolver", { estado: "descartada" }),
    );
  });

  it("lets a moderador resolve", async () => {
    mockUseAuthStore.mockReturnValue({ user: { user_metadata: { org_role: "moderador" } } });
    mockRoutes();
    mockPost.mockResolvedValue({ ...FLAG, estado: "resolvida" });
    const { default: Moderacao } = await import("../Moderacao");
    renderPage(<Moderacao />);
    await waitFor(() => expect(screen.getByTestId("flag-resolver-f-1")).toBeEnabled());
    fireEvent.click(screen.getByTestId("flag-resolver-f-1"));
    await waitFor(() => expect(mockPost).toHaveBeenCalled());
  });

  it("shows the honest empty state", async () => {
    mockRoutes({ items: [], total: 0 });
    const { default: Moderacao } = await import("../Moderacao");
    renderPage(<Moderacao />);
    await waitFor(() => expect(screen.getByText("Nenhuma mensagem sinalizada")).toBeInTheDocument());
  });

  it("notes when WhatsApp is not connected", async () => {
    mockRoutes();
    mockGet.mockImplementation((path: string) =>
      path === "/api/whatsapp/sessao"
        ? Promise.resolve({ estado: "NAO_CONFIGURADO", sessao: "default" })
        : path === "/api/whatsapp/flags"
          ? Promise.resolve({ items: [], total: 0 })
          : Promise.resolve({ items: [], total: 0 }),
    );
    const { default: Moderacao } = await import("../Moderacao");
    renderPage(<Moderacao />);
    await waitFor(() => expect(screen.getByTestId("moderacao-whatsapp-indisponivel")).toBeInTheDocument());
  });
});
