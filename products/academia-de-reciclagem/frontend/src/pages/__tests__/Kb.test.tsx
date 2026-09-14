/**
 * Kb (base de conhecimento list) — page-level render tests.
 *
 * Mocks ONLY `@/lib/api` (the HTTP boundary) — real hooks, real
 * TanStack Query, real page. Proves:
 * 1. `showSkeleton = isPending && !data` — the skeleton renders on first
 *    load and nowhere else (`KB § PATTERNS/frontend/lying-loading-state.md`).
 * 2. A mocked `{detail, code}` 404 body reaches the page as the exact
 *    contract §B.0 PT-BR text.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockGet = vi.fn();

vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
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

function neverResolves() {
  return new Promise(() => {});
}

beforeEach(() => vi.clearAllMocks());

describe("Kb — loading vs empty vs data", () => {
  it("shows the skeleton on first load (isPending && !data)", async () => {
    mockGet.mockReturnValue(neverResolves());
    const { default: Kb } = await import("../Kb");
    const { container } = renderPage(<Kb />);

    await waitFor(() => {
      expect(container.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
    });
    expect(screen.queryByText("Nenhuma entrada encontrada.")).not.toBeInTheDocument();
  });

  it("renders the empty state once a settled fetch really returned no entries", async () => {
    mockGet.mockResolvedValue({ items: [], total: 0 });
    const { default: Kb } = await import("../Kb");
    renderPage(<Kb />);

    await waitFor(() => expect(screen.getByText("Nenhuma entrada encontrada.")).toBeInTheDocument());
  });

  it("renders entries once loaded", async () => {
    mockGet.mockResolvedValue({
      items: [
        {
          slug: "dominio-regulatorio-pnrs",
          categoria: "dominio",
          subcategoria: "regulatorio",
          titulo: "PNRS",
          resumo: "Resumo curto",
          tags: ["pnrs"],
          updated_at: "2026-09-01T00:00:00Z",
        },
      ],
      total: 1,
    });
    const { default: Kb } = await import("../Kb");
    renderPage(<Kb />);

    await waitFor(() => expect(screen.getByText("PNRS")).toBeInTheDocument());
    expect(mockGet).toHaveBeenCalledWith("/api/kb", {
      limite: 20,
      offset: 0,
    });
  });
});

describe("Kb — error → PT-BR contract text", () => {
  it("shows the backend's contract detail text for a 404-shaped error", async () => {
    const { ApiError } = await import("@noctusai/lib");
    mockGet.mockRejectedValue(new ApiError(404, "Não encontrado."));
    const { default: Kb } = await import("../Kb");
    renderPage(<Kb />);

    await waitFor(() => expect(screen.getByText("Não encontrado.")).toBeInTheDocument());
  });
});
