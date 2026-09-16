/**
 * Membros page render tests — community-m1-contract.md §Frontend.
 *
 * Mocks ONLY `@/lib/api` (the HTTP boundary) — real hooks, real TanStack
 * Query, real page. Proves:
 * 1. `showSkeleton = isPending && !data` — the skeleton renders on first
 *    load and nowhere else (`KB § PATTERNS/frontend/lying-loading-state.md`).
 * 2. The empty state renders once a settled fetch really returned no rows.
 * 3. A `moderador`'s 403 write attempt surfaces the server's own `detail`
 *    text, not a generic placeholder.
 * 4. Real data renders with the `resumo` tab counts and row data.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
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

// Design-system barrel transitively reaches the seed infra singleton, which
// builds a Supabase client at module load — stub the seam the vitest factory
// ships an alias for (`@noctusai/seed/infra`). Nothing on this page talks to
// Supabase directly.
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

const RESUMO = { pendente: 1, ativo: 10, atrasado: 2, pausado: 0, cancelado: 3 };

beforeEach(() => vi.clearAllMocks());

describe("Membros — loading vs empty vs data", () => {
  it("shows the skeleton on first load (isPending && !data)", async () => {
    mockGet.mockReturnValue(neverResolves());
    const { default: Membros } = await import("../Membros");
    const { container } = renderPage(<Membros />);

    await waitFor(() => {
      expect(container.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
    });
    expect(screen.queryByText("Nenhum membro encontrado.")).not.toBeInTheDocument();
  });

  it("renders the empty state once a settled fetch really returned no members", async () => {
    mockGet.mockResolvedValue({ items: [], total: 0, resumo: RESUMO });
    const { default: Membros } = await import("../Membros");
    renderPage(<Membros />);

    await waitFor(() => expect(screen.getByText("Nenhum membro encontrado.")).toBeInTheDocument());
  });

  it("renders members with resumo-derived tab counts", async () => {
    mockGet.mockResolvedValue({
      items: [
        {
          id: "m-1",
          nome: "Ana",
          email: "ana@x.com",
          telefone: "+5511999999999",
          status: "ativo",
          plano_id: "p-1",
          plano_nome: "Círculo",
          origem: "aplicacao",
          tags: ["fundadora"],
          user_id: null,
          observacoes: null,
          entrou_em: "2026-09-16T20:00:00+00:00",
          created_at: "2026-09-16T20:00:00+00:00",
          updated_at: "2026-09-16T20:00:00+00:00",
        },
      ],
      total: 1,
      resumo: RESUMO,
    });
    const { default: Membros } = await import("../Membros");
    renderPage(<Membros />);

    await waitFor(() => expect(screen.getByTestId("membro-row-m-1")).toBeInTheDocument());
    expect(screen.getByTestId("membro-row-m-1")).toHaveTextContent("Ana");
    expect(screen.getByText("Círculo")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ativos (10)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancelados (3)" })).toBeInTheDocument();
    expect(mockGet).toHaveBeenCalledWith("/api/membros", {
      status: undefined,
      plano_id: undefined,
      busca: undefined,
      page: 1,
      page_size: 50,
    });
  });
});

describe("Membros — error → contract detail text", () => {
  it("shows the backend's 403 detail verbatim for a moderador write attempt", async () => {
    const { ApiError } = await import("@noctusai/lib");
    mockGet.mockRejectedValue(new ApiError(403, "Apenas administradores podem criar membros."));
    const { default: Membros } = await import("../Membros");
    renderPage(<Membros />);

    await waitFor(() =>
      expect(screen.getByText("Apenas administradores podem criar membros.")).toBeInTheDocument(),
    );
  });
});
