/**
 * Planos page render tests — community-m1-contract.md §Frontend,
 * community-m2-contract.md §Frontend (gateway-ref extension).
 *
 * The page consumes `<ResourceManager/>` (`@noctusai/lib/components`)
 * rather than building its own fetch/table — these tests exercise the
 * organ's own loading/empty/error/success states through the page's real
 * `columns`/`fields`/`toForm`/`toPayload` wiring, plus the money
 * cents↔reais conversion. `renderPage` now wraps a `QueryClientProvider` —
 * the module 2 extension (`GatewayRefsBadges`/`GatewayRefsDialog`) uses
 * TanStack Query hooks, which module 1's original self-contained
 * `<ResourceManager/>` did not require.
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
const mockPut = vi.fn();
const mockDelete = vi.fn();

vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: mockPost, put: mockPut, patch: mockPatch, delete: mockDelete },
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

describe("Planos — gateway refs extension (community-m2-contract.md)", () => {
  function routeGet(planoGatewayRefs: { items: unknown[]; total: number }) {
    mockGet.mockImplementation((path: string) => {
      if (path.includes("/gateway-refs")) return Promise.resolve(planoGatewayRefs);
      return Promise.resolve({ items: [PLANO], total: 1 });
    });
  }

  it("badges show 'não disponível' for a plano with no gateway refs yet", async () => {
    routeGet({ items: [], total: 0 });
    const { default: Planos } = await import("../Planos");
    renderPage(<Planos />);

    await waitFor(() => expect(screen.getAllByText(/não disponível/).length).toBe(2));
  });

  it("badges show the gateway as configured once a ref exists", async () => {
    routeGet({
      items: [{ plano_id: "p-1", gateway: "stripe", ref_externo: "price_123", updated_at: "2026-09-16T20:00:00+00:00" }],
      total: 1,
    });
    const { default: Planos } = await import("../Planos");
    renderPage(<Planos />);

    await waitFor(() => expect(screen.getByText("Stripe (cartão)")).toBeInTheDocument());
    expect(screen.getByText(/Asaas \(Pix \/ boleto\) — não disponível/)).toBeInTheDocument();
  });

  it("opens the Gateways dialog and saves a ref via PUT (upsert)", async () => {
    routeGet({ items: [], total: 0 });
    mockPut.mockResolvedValue({
      plano_id: "p-1",
      gateway: "stripe",
      ref_externo: "price_999",
      updated_at: "2026-09-16T20:00:00+00:00",
    });
    const { default: Planos } = await import("../Planos");
    renderPage(<Planos />);

    await waitFor(() => expect(screen.getByText("Círculo")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Gateways" }));

    await waitFor(() => expect(screen.getByText("Stripe (cartão)")).toBeInTheDocument());
    const [stripeInput] = screen.getAllByPlaceholderText("Referência externa");
    fireEvent.change(stripeInput, { target: { value: "price_999" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Salvar" })[0]);

    await waitFor(() =>
      expect(mockPut).toHaveBeenCalledWith("/api/planos/p-1/gateway-refs/stripe", { ref_externo: "price_999" }),
    );
  });
});
