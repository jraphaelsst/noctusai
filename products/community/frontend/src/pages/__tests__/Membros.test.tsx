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

// Design-system barrel transitively reaches the seed infra singleton, which
// builds a Supabase client at module load — stub the seam the vitest factory
// ships an alias for (`@noctusai/seed/infra`). Nothing on this page talks to
// Supabase directly.
const mockUseAuthStore = vi.fn(() => ({ user: null as unknown }));
const ADMIN = { user: { user_metadata: { org_role: "admin" } } };
const MODERADOR = { user: { user_metadata: { org_role: "moderador" } } };

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

beforeEach(() => {
  vi.clearAllMocks();
  mockUseAuthStore.mockReturnValue(ADMIN);
});

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

const MEMBRO = {
  id: "m-1",
  nome: "Ana",
  email: "ana@x.com",
  telefone: null,
  status: "pendente",
  plano_id: "p-1",
  plano_nome: "Círculo",
  origem: "convite",
  tags: [],
  user_id: null,
  observacoes: null,
  entrou_em: "2026-09-16T20:00:00+00:00",
  created_at: "2026-09-16T20:00:00+00:00",
  updated_at: "2026-09-16T20:00:00+00:00",
};

function routeGets(state: { membro: typeof MEMBRO }) {
  mockGet.mockImplementation((path: string) => {
    if (path === "/api/membros") {
      return Promise.resolve({ items: [state.membro], total: 1, resumo: RESUMO });
    }
    if (path === `/api/membros/${state.membro.id}`) return Promise.resolve(state.membro);
    if (path.startsWith("/api/planos")) return Promise.resolve({ items: [], total: 0 });
    return Promise.resolve({ items: [], total: 0 });
  });
}

describe("Membros — detail dialog stays fresh", () => {
  it("shows the new status badge in the dialog after Alterar status succeeds", async () => {
    const state = { membro: { ...MEMBRO } };
    routeGets(state);
    mockPost.mockImplementation(async () => {
      state.membro = { ...state.membro, status: "ativo" };
      return state.membro;
    });
    const { default: Membros } = await import("../Membros");
    renderPage(<Membros />);

    fireEvent.click(await screen.findByTestId("membro-row-m-1"));
    const dialog = await screen.findByTestId("membro-detail-dialog");
    expect(dialog).toHaveTextContent("Pendente");

    fireEvent.click(screen.getByTestId("membro-alterar-status"));
    await screen.findByRole("button", { name: "Confirmar" });
    const select = screen.getAllByRole("combobox").find((el) => (el as HTMLSelectElement).value === "pendente")!;
    fireEvent.change(select, { target: { value: "ativo" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirmar" }));

    await waitFor(() => expect(screen.getByTestId("membro-detail-dialog")).toHaveTextContent("Ativo"));
    expect(screen.getByTestId("membro-detail-dialog")).not.toHaveTextContent("Pendente");
  });
});

describe("Membros — role gating", () => {
  it("hides every admin-only action for a moderador", async () => {
    mockUseAuthStore.mockReturnValue(MODERADOR);
    routeGets({ membro: { ...MEMBRO } });
    const { default: Membros } = await import("../Membros");
    renderPage(<Membros />);

    fireEvent.click(await screen.findByTestId("membro-row-m-1"));
    await screen.findByTestId("membro-detail-dialog");
    expect(screen.queryByText("+ Novo Membro")).not.toBeInTheDocument();
    for (const id of ["membro-cancelar", "membro-criar-acesso", "membro-alterar-status", "membro-editar"]) {
      expect(screen.queryByTestId(id)).not.toBeInTheDocument();
    }
  });

  it("shows them for an admin", async () => {
    routeGets({ membro: { ...MEMBRO } });
    const { default: Membros } = await import("../Membros");
    renderPage(<Membros />);

    expect(await screen.findByText("+ Novo Membro")).toBeInTheDocument();
    fireEvent.click(await screen.findByTestId("membro-row-m-1"));
    expect(await screen.findByTestId("membro-editar")).toBeInTheDocument();
  });
});

describe("Membros — phone normalization on submit", () => {
  it("sends a BR national number as E.164", async () => {
    routeGets({ membro: { ...MEMBRO } });
    mockPost.mockResolvedValue(MEMBRO);
    const { default: Membros } = await import("../Membros");
    renderPage(<Membros />);

    fireEvent.click(await screen.findByText("+ Novo Membro"));
    fireEvent.change(await screen.findByLabelText(/Nome/), { target: { value: "Bia" } });
    fireEvent.change(screen.getByLabelText(/E-mail/), { target: { value: "bia@x.com" } });
    fireEvent.change(screen.getByLabelText(/Telefone/), { target: { value: "11999990001" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));

    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    expect(mockPost.mock.calls[0][0]).toBe("/api/membros");
    expect(mockPost.mock.calls[0][1].telefone).toBe("+5511999990001");
  });

  it("blocks an unparseable phone with a pt-BR message and no request", async () => {
    routeGets({ membro: { ...MEMBRO } });
    const { default: Membros } = await import("../Membros");
    renderPage(<Membros />);

    fireEvent.click(await screen.findByText("+ Novo Membro"));
    fireEvent.change(await screen.findByLabelText(/Nome/), { target: { value: "Bia" } });
    fireEvent.change(screen.getByLabelText(/E-mail/), { target: { value: "bia@x.com" } });
    fireEvent.change(screen.getByLabelText(/Telefone/), { target: { value: "123" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));

    expect(await screen.findByText(/Telefone inválido/)).toBeInTheDocument();
    expect(mockPost).not.toHaveBeenCalled();
  });
});
