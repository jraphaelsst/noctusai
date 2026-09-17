/**
 * Transmissões page render tests — community-m3-contract.md §4.
 *
 * Proves the two loading signals, the empty/error states, that "Enviar"
 * requires a confirmation before firing `POST .../enviar`, and that the
 * per-destino delivery table renders from the embedded `destinos` field.
 */
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

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

function renderPage(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

const TRANSMISSAO_RASCUNHO = {
  id: "t-1",
  titulo: "Aviso de manutenção",
  corpo: "O sistema ficará indisponível às 22h.",
  tipo: "anuncio",
  estado: "rascunho",
  agendada_para: null,
  enviada_em: null,
  criada_por: "u-1",
  destinos: [],
};

const TRANSMISSAO_ENVIADA = {
  ...TRANSMISSAO_RASCUNHO,
  id: "t-2",
  estado: "enviada",
  enviada_em: "2026-09-15T10:00:00+00:00",
  destinos: [
    { id: "d-1", grupo_id: "g-1", grupo_nome: "Comunidade Oficial", estado: "enviado", provider_message_id: "wamid1", erro: null, enviado_em: "2026-09-15T10:00:01+00:00" },
    { id: "d-2", grupo_id: "g-2", grupo_nome: "VIP", estado: "falhou", provider_message_id: null, erro: "Grupo não encontrado", enviado_em: null },
  ],
};

function mockRoutes(overrides: Record<string, unknown> = {}) {
  mockGet.mockImplementation((path: string) => {
    if (path === "/api/whatsapp/transmissoes") {
      return Promise.resolve(overrides.transmissoes ?? { items: [TRANSMISSAO_RASCUNHO], total: 1 });
    }
    if (path === "/api/whatsapp/grupos") {
      return Promise.resolve(overrides.grupos ?? { items: [{ id: "g-1", nome: "Comunidade Oficial", ativo: true }], total: 1 });
    }
    return Promise.reject(new Error(`unexpected GET ${path}`));
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("confirm", vi.fn(() => true));
});

describe("Transmissoes — loading + empty + list", () => {
  it("shows the loading skeleton, then renders the list", async () => {
    mockRoutes();
    const { default: Transmissoes } = await import("../Transmissoes");
    renderPage(<Transmissoes />);

    await waitFor(() => expect(screen.getByTestId("transmissao-row-t-1")).toBeInTheDocument());
    expect(screen.getByTestId("transmissao-row-t-1")).toHaveTextContent("Aviso de manutenção");
  });

  it("renders the empty state with no transmissões", async () => {
    mockRoutes({ transmissoes: { items: [], total: 0 } });
    const { default: Transmissoes } = await import("../Transmissoes");
    renderPage(<Transmissoes />);

    await waitFor(() => expect(screen.getByText("Nenhuma transmissão ainda.")).toBeInTheDocument());
  });
});

describe("Transmissoes — enviar requires confirmation", () => {
  it("confirms before calling POST .../enviar", async () => {
    mockRoutes();
    mockPost.mockResolvedValue({ transmissao_id: "t-1", destinos: 1 });
    const { default: Transmissoes } = await import("../Transmissoes");
    renderPage(<Transmissoes />);

    await waitFor(() => expect(screen.getByTestId("transmissao-enviar-t-1")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("transmissao-enviar-t-1"));

    expect(window.confirm).toHaveBeenCalled();
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith("/api/whatsapp/transmissoes/t-1/enviar", {}));
  });
});

describe("Transmissoes — per-destino delivery table", () => {
  it("renders the embedded destinos with estado and erro", async () => {
    mockRoutes({ transmissoes: { items: [TRANSMISSAO_ENVIADA], total: 1 } });
    const { default: Transmissoes } = await import("../Transmissoes");
    renderPage(<Transmissoes />);

    await waitFor(() => expect(screen.getByTestId("transmissao-row-t-2")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("transmissao-row-t-2"));

    await waitFor(() => expect(screen.getByTestId("transmissao-destinos-tabela")).toBeInTheDocument());
    expect(screen.getByTestId("destino-row-d-1")).toHaveTextContent("Comunidade Oficial");
    expect(screen.getByTestId("destino-row-d-2")).toHaveTextContent("Grupo não encontrado");
  });
});
