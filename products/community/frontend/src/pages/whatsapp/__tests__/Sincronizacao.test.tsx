/**
 * Sincronização page render tests — community-m3-contract.md §4, the
 * confirm-then-apply safety flow.
 *
 * Proves:
 * 1. "Aplicar" is disabled while `estado === "proposto"` (never collapsed
 *    with "Confirmar" into one click).
 * 2. "Confirmar" stays disabled until BOTH the checkbox is checked AND the
 *    typed confirmation text matches — checking only one is not enough.
 * 3. The per-participant preview always masks the phone to the last 4
 *    digits.
 * 4. `aplicado_parcial` renders as a warning (not a quiet success) with
 *    per-item outcome badges, and "Repetir o restante" creates a brand-new
 *    lote (a fresh `POST .../lotes` call) rather than mutating this one.
 * 5. "Convites pendentes" is admin-only — absent from the DOM for a
 *    moderador even when the lote has a `convite_necessario` item.
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

const FUTURE = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();

function buildLote(overrides: Record<string, unknown> = {}) {
  return {
    id: "l-1",
    grupo_id: "g-1",
    grupo_nome: "Comunidade Oficial",
    acao: "adicionar",
    estado: "proposto",
    total_itens: 1,
    proposto_por: "u-1",
    confirmado_por: null,
    proposto_em: "2026-09-15T00:00:00+00:00",
    confirmado_em: null,
    aplicado_em: null,
    expira_em: FUTURE,
    motivo_falha: null,
    itens: [
      {
        id: "li-1",
        membro_id: "m-1",
        membro_nome: "Ana",
        participante_jid: "5511999999999@c.us",
        telefone: "+5511999991234",
        resultado: "pendente",
        codigo_waha: null,
        processado_em: null,
      },
    ],
    ignorados: [],
    ...overrides,
  };
}

function mockRoutes(lote: ReturnType<typeof buildLote>, extra: Record<string, unknown> = {}) {
  mockGet.mockImplementation((path: string) => {
    if (path === "/api/whatsapp/lotes") return Promise.resolve({ items: [lote], total: 1 });
    if (path === "/api/whatsapp/lotes/l-1") return Promise.resolve(lote);
    if (path === "/api/whatsapp/grupos") return Promise.resolve({ items: [{ id: "g-1", nome: "Comunidade Oficial" }], total: 1 });
    if (path === "/api/whatsapp/lotes/l-1/convites-pendentes") {
      return Promise.resolve(extra.convitesPendentes ?? { items: [], total: 0, link: null });
    }
    return Promise.reject(new Error(`unexpected GET ${path}`));
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseAuthStore.mockReturnValue({ user: null });
  mockPost.mockResolvedValue({});
});

describe("Sincronizacao — confirm-then-apply gating", () => {
  it("masks the phone in the preview and disables Aplicar while proposto", async () => {
    mockRoutes(buildLote());
    const { default: Sincronizacao } = await import("../Sincronizacao");
    renderPage(<Sincronizacao />);

    await waitFor(() => expect(screen.getByTestId("lote-row-l-1")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("lote-row-l-1"));

    await waitFor(() => expect(screen.getByTestId("lote-item-telefone-li-1")).toBeInTheDocument());
    expect(screen.getByTestId("lote-item-telefone-li-1")).toHaveTextContent("1234");
    expect(screen.getByTestId("lote-item-telefone-li-1")).not.toHaveTextContent("+5511999991234");

    expect(screen.getByTestId("lote-aplicar")).toBeDisabled();
  });

  it("keeps Confirmar disabled until BOTH the checkbox and the typed phrase are set", async () => {
    mockRoutes(buildLote());
    const { default: Sincronizacao } = await import("../Sincronizacao");
    renderPage(<Sincronizacao />);

    await waitFor(() => expect(screen.getByTestId("lote-row-l-1")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("lote-row-l-1"));
    await waitFor(() => expect(screen.getByTestId("lote-confirmar")).toBeInTheDocument());

    expect(screen.getByTestId("lote-confirmar")).toBeDisabled();

    fireEvent.click(screen.getByTestId("lote-confirmo-checkbox"));
    expect(screen.getByTestId("lote-confirmar")).toBeDisabled();

    fireEvent.change(screen.getByTestId("lote-confirmo-texto"), { target: { value: "confirmar" } });
    expect(screen.getByTestId("lote-confirmar")).not.toBeDisabled();

    fireEvent.click(screen.getByTestId("lote-confirmo-checkbox")); // unchecked again
    expect(screen.getByTestId("lote-confirmar")).toBeDisabled();
  });

  it("enables Aplicar once confirmado, and Confirmar is gone", async () => {
    mockRoutes(buildLote({ estado: "confirmado", confirmado_em: "2026-09-15T01:00:00+00:00" }));
    const { default: Sincronizacao } = await import("../Sincronizacao");
    renderPage(<Sincronizacao />);

    await waitFor(() => expect(screen.getByTestId("lote-row-l-1")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("lote-row-l-1"));

    await waitFor(() => expect(screen.getByTestId("lote-aplicar")).toBeInTheDocument());
    expect(screen.getByTestId("lote-aplicar")).not.toBeDisabled();
    expect(screen.queryByTestId("lote-confirmar")).not.toBeInTheDocument();
  });
});

describe("Sincronizacao — aplicado_parcial", () => {
  it("renders a warning (not a quiet success) with per-item badges, and Repetir creates a NEW lote", async () => {
    const lote = buildLote({
      estado: "aplicado_parcial",
      itens: [
        { id: "li-1", membro_id: "m-1", membro_nome: "Ana", participante_jid: "a@c.us", telefone: "+5511999991234", resultado: "adicionado", codigo_waha: 200, processado_em: "2026-09-15T02:00:00+00:00" },
        { id: "li-2", membro_id: "m-2", membro_nome: "Bia", participante_jid: "b@c.us", telefone: "+5511999995678", resultado: "falhou", codigo_waha: 500, processado_em: "2026-09-15T02:00:00+00:00" },
      ],
    });
    mockRoutes(lote);
    const { default: Sincronizacao } = await import("../Sincronizacao");
    renderPage(<Sincronizacao />);

    await waitFor(() => expect(screen.getByTestId("lote-row-l-1")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("lote-row-l-1"));

    await waitFor(() => expect(screen.getByTestId("lote-aviso-parcial")).toBeInTheDocument());
    expect(screen.getByTestId("lote-item-resultado-li-1")).toHaveTextContent("Adicionado");
    expect(screen.getByTestId("lote-item-resultado-li-2")).toHaveTextContent("Falhou");

    fireEvent.click(screen.getByTestId("lote-repetir-restante"));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith("/api/whatsapp/grupos/g-1/lotes", { acao: "adicionar" }));
    // Never a call that mutates the already-applied lote l-1.
    expect(mockPost).not.toHaveBeenCalledWith("/api/whatsapp/lotes/l-1/aplicar", expect.anything());
  });
});

describe("Sincronizacao — Convites pendentes (admin-only)", () => {
  const parcialComConvite = buildLote({
    estado: "aplicado_parcial",
    itens: [
      { id: "li-1", membro_id: "m-1", membro_nome: "Ana", participante_jid: "a@c.us", telefone: "+5511999991234", resultado: "convite_necessario", codigo_waha: 403, processado_em: "2026-09-15T02:00:00+00:00" },
    ],
  });

  it("admin: shows the panel with the group's invite link", async () => {
    mockUseAuthStore.mockReturnValue({ user: { user_metadata: { org_role: "admin" } } });
    mockRoutes(parcialComConvite, {
      convitesPendentes: { items: [{ membro_id: "m-1", nome: "Ana", telefone: "+5511999991234", participante_jid: "a@c.us" }], total: 1, link: "https://chat.whatsapp.com/abc123" },
    });
    const { default: Sincronizacao } = await import("../Sincronizacao");
    renderPage(<Sincronizacao />);

    await waitFor(() => expect(screen.getByTestId("lote-row-l-1")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("lote-row-l-1"));

    await waitFor(() => expect(screen.getByTestId("convites-pendentes-link")).toBeInTheDocument());
    expect(screen.getByTestId("convites-pendentes-link")).toHaveTextContent("https://chat.whatsapp.com/abc123");
  });

  it("moderador: the panel is ABSENT from the DOM, and the endpoint is never called", async () => {
    mockUseAuthStore.mockReturnValue({ user: { user_metadata: { org_role: "moderador" } } });
    mockRoutes(parcialComConvite);
    const { default: Sincronizacao } = await import("../Sincronizacao");
    renderPage(<Sincronizacao />);

    await waitFor(() => expect(screen.getByTestId("lote-row-l-1")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("lote-row-l-1"));

    await waitFor(() => expect(screen.getByTestId("lote-aviso-parcial")).toBeInTheDocument());
    expect(screen.queryByTestId("convites-pendentes-panel")).not.toBeInTheDocument();
    expect(mockGet).not.toHaveBeenCalledWith("/api/whatsapp/lotes/l-1/convites-pendentes");
  });
});
