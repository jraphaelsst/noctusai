/**
 * Planos page render tests — community-m1-contract.md §Frontend.
 *
 * The page consumes `<ResourceManager/>` (`@noctusai/lib/components`)
 * rather than building its own fetch/table — these tests exercise the
 * organ's own loading/empty/error/success states through the page's real
 * `columns`/`fields`/`toForm`/`toPayload` wiring, plus the money
 * cents↔reais conversion.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { MemoryRouter } from "react-router-dom";

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
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

function neverResolves() {
  return new Promise(() => {});
}

const PLANO = {
  id: "p-1",
  nome: "Círculo",
  descricao: null,
  preco_centavos: 9900,
  ciclo: "mensal",
  entitlements: {
    feed: true,
    forum: false,
    chat: true,
    eventos: false,
    conteudo_ids: [],
    grupos_whatsapp: [],
    conteudo_todos: false,
  },
  ativo: true,
  ordem: 0,
  membros_ativos: 12,
  created_at: "2026-09-16T20:00:00+00:00",
  updated_at: "2026-09-16T20:00:00+00:00",
};

beforeEach(() => vi.clearAllMocks());

describe("Planos — loading vs empty vs data", () => {
  it("shows the ResourceManager loading state on first fetch", async () => {
    mockGet.mockReturnValue(neverResolves());
    const { default: Planos } = await import("../Planos");
    renderPage(<Planos />);

    await waitFor(() => expect(screen.getByRole("status", { name: "Carregando" })).toBeInTheDocument());
  });

  it("renders the empty state once a settled fetch really returned no planos", async () => {
    mockGet.mockResolvedValue({ items: [], total: 0 });
    const { default: Planos } = await import("../Planos");
    renderPage(<Planos />);

    await waitFor(() => expect(screen.getByText(/Nenhum plano cadastrado/)).toBeInTheDocument());
  });

  it("renders planos with BRL-formatted price and membros_ativos", async () => {
    mockGet.mockResolvedValue({ items: [PLANO], total: 1 });
    const { default: Planos } = await import("../Planos");
    renderPage(<Planos />);

    await waitFor(() => expect(screen.getByText("Círculo")).toBeInTheDocument());
    expect(screen.getByText("R$ 99,00")).toBeInTheDocument();
    expect(screen.getByText("Mensal")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
  });
});

describe("Planos — error state", () => {
  it("shows the backend's detail message on a failed fetch", async () => {
    mockGet.mockRejectedValue(new Error("Falha ao carregar plano"));
    const { default: Planos } = await import("../Planos");
    renderPage(<Planos />);

    await waitFor(() => expect(screen.getByText("Falha ao carregar plano")).toBeInTheDocument());
  });
});
