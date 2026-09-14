/**
 * Roadmap — page-level render + kanban-move-wiring tests.
 *
 * Mocks `@/lib/api` (the HTTP boundary — real hooks run against it) plus
 * `@noctusai/lib/components`'s `KanbanBoard` ITSELF for the move test only:
 * jsdom has no layout, so `@dnd-kit`'s collision detection cannot be driven
 * by a real pointer drag (documented limitation of the organ itself — see
 * `KanbanBoard.tsx`'s header and `products/orbity/frontend/src/pages/
 * __tests__/Funil.test.tsx`). Capturing the `onMove` callback the page wires
 * up and invoking it directly is the nearest in-jsdom proof that a card move
 * really calls `PATCH /api/tasks/{codigo}` — the mutation, not the drag
 * physics, is this page's own logic to prove.
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

vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: mockPost, put: vi.fn(), patch: mockPatch, delete: vi.fn() },
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

const capturedOnMove = vi.fn();

vi.mock("@noctusai/lib/components", () => ({
  // Minimal stand-in that just captures onMove + renders card codes, so the
  // test can invoke the page's real wiring without a physical drag.
  KanbanBoard: (props: {
    columns: { stage: { id: string; label: string }; cards: { codigo: string }[] }[];
    onMove: (cardId: string, from: string, to: string, toIndex: number) => void;
  }) => {
    capturedOnMove.mockImplementation(props.onMove);
    return (
      <div data-testid="kanban-stub">
        {props.columns.map((c) => (
          <div key={c.stage.id} data-kanban-column-id={c.stage.id}>
            {c.cards.map((card) => (
              <div key={card.codigo} data-kanban-card-id={card.codigo} />
            ))}
          </div>
        ))}
      </div>
    );
  },
}));

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

const PHASE = {
  codigo: "P1",
  titulo: "Fundação",
  objetivo: "Migrar o conhecimento",
  concluida_quando: "Todas as entidades importadas",
  estado: "em-andamento",
  ordem: 1,
};

const TASK = {
  codigo: "T-005",
  titulo: "Construir o parser do bundle",
  fase: "P1",
  detalhe: null,
  estado: "pendente",
  bloqueada_por: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  mockGet.mockImplementation((path: string) => {
    if (path === "/api/roadmap") return Promise.resolve({ items: [PHASE], total: 1 });
    if (path === "/api/tasks") return Promise.resolve({ items: [TASK], total: 1 });
    return Promise.reject(new Error(`unexpected GET ${path}`));
  });
});

describe("Roadmap — kanban organ really mounted", () => {
  it("groups the task under its estado column", async () => {
    const { default: Roadmap } = await import("../Roadmap");
    const { container } = renderPage(<Roadmap />);

    await waitFor(() => expect(screen.getByTestId("kanban-stub")).toBeInTheDocument());
    const pendenteColumn = container.querySelector('[data-kanban-column-id="pendente"]');
    expect(pendenteColumn?.querySelector('[data-kanban-card-id="T-005"]')).toBeInTheDocument();
  });
});

describe("Roadmap — moving a card PATCHes the task", () => {
  it("calls PATCH /api/tasks/{codigo} with the new estado on a cross-column move", async () => {
    mockPatch.mockResolvedValue({ ...TASK, estado: "em-andamento" });
    const { default: Roadmap } = await import("../Roadmap");
    renderPage(<Roadmap />);

    await waitFor(() => expect(screen.getByTestId("kanban-stub")).toBeInTheDocument());

    // Fire the wiring Roadmap.tsx attached to KanbanBoard's onMove.
    capturedOnMove("T-005", "pendente", "em-andamento", 0);

    await waitFor(() =>
      expect(mockPatch).toHaveBeenCalledWith("/api/tasks/T-005", { estado: "em-andamento" }),
    );
  });

  it("does not PATCH on a same-column reorder (fromStage === toStage)", async () => {
    const { default: Roadmap } = await import("../Roadmap");
    renderPage(<Roadmap />);

    await waitFor(() => expect(screen.getByTestId("kanban-stub")).toBeInTheDocument());

    capturedOnMove("T-005", "pendente", "pendente", 1);

    expect(mockPatch).not.toHaveBeenCalled();
  });
});
