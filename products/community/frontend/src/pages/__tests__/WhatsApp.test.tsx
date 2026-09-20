/**
 * WhatsApp page render tests — community-m3-contract.md §4.
 *
 * `mockGet` routes by path since the page fires `/api/whatsapp/sessao`,
 * `/api/whatsapp/grupos`, and (once a row is opened) `/api/whatsapp/grupos/
 * {id}` — the roster ships EMBEDDED in that detail response (`.membros`),
 * never a separate `/membros` endpoint (2026-09-20 wiring audit, task 7:
 * that endpoint was never built and 404'd on every drawer open) — plus
 * `/api/whatsapp/grupos/{id}/convite` only on an admin's click-to-reveal.
 *
 * Proves:
 * 1. Two loading signals (`showSkeleton`/`isRefreshing`), never `isLoading`.
 * 2. The session banner distinguishes WORKING from needing pairing, and
 *    never implies a QR endpoint exists.
 * 3. The invite-link section renders for an admin and is genuinely ABSENT
 *    from the DOM for a moderador (not merely hidden) — asserted via
 *    `queryByTestId` returning null, not a CSS/visibility check.
 * 4. Phones in the roster always render masked to the last 4 digits.
 * 5. The roster comes from the SAME detail request the drawer already
 *    makes — no second GET to a `/membros` path (task 7 regression).
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

vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: mockPost, put: vi.fn(), patch: mockPatch, delete: vi.fn() },
}));

const mockUseAuthStore = vi.fn(() => ({ user: null as unknown }));
const mockNavigate = vi.fn();

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

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
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

const GRUPO = {
  id: "g-1",
  nome: "Comunidade Oficial",
  chat_id: "12036xxxx@g.us",
  descricao: null,
  ativo: true,
  somente_admin: false,
  participantes_observados: 12,
  membros_elegiveis: 15,
  sincronizado_em: "2026-09-10T00:00:00+00:00",
  created_at: "2026-09-01T00:00:00+00:00",
  updated_at: "2026-09-01T00:00:00+00:00",
};

const ROSTER_ITEM = {
  participante_jid: "5511999999999@c.us",
  membro_id: "m-1",
  membro_nome: "Ana",
  telefone: "+5511999991234",
  papel: "participante",
  visto_em: "2026-09-10T00:00:00+00:00",
};

function mockRoutes(overrides: Record<string, unknown> = {}) {
  mockGet.mockImplementation((path: string) => {
    if (path === "/api/whatsapp/sessao") {
      return Promise.resolve(overrides.sessao ?? { estado: "WORKING", sessao: "default" });
    }
    if (path === "/api/whatsapp/grupos") {
      return Promise.resolve(overrides.grupos ?? { items: [GRUPO], total: 1 });
    }
    // The roster ships embedded in the DETAIL response (`.membros`) — no
    // separate `/membros` route exists (task 7).
    if (path === `/api/whatsapp/grupos/${GRUPO.id}`) {
      return Promise.resolve(
        overrides.grupoDetail ?? { ...GRUPO, membros: [ROSTER_ITEM] },
      );
    }
    if (path === `/api/whatsapp/grupos/${GRUPO.id}/convite`) {
      if (overrides.conviteError) return Promise.reject(overrides.conviteError);
      return Promise.resolve(overrides.convite ?? { link: "https://chat.whatsapp.com/abc123" });
    }
    return Promise.reject(new Error(`unexpected GET ${path}`));
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseAuthStore.mockReturnValue({ user: null });
});

describe("WhatsApp — loading + session banner", () => {
  it("shows the loading skeleton, then the session banner and groups table", async () => {
    mockRoutes();
    const { default: WhatsApp } = await import("../WhatsApp");
    renderPage(<WhatsApp />);

    await waitFor(() => expect(screen.getByTestId("sessao-banner")).toBeInTheDocument());
    expect(screen.getByTestId("sessao-banner")).toHaveTextContent("Conectado");
    await waitFor(() => expect(screen.getByTestId("grupo-row-g-1")).toBeInTheDocument());
    expect(screen.getByTestId("grupo-row-g-1")).toHaveTextContent("Comunidade Oficial");
  });

  it("explains pairing is an operator action when the session needs pairing, never implying a QR endpoint", async () => {
    mockRoutes({ sessao: { estado: "SCAN_QR_CODE", sessao: "default" } });
    const { default: WhatsApp } = await import("../WhatsApp");
    renderPage(<WhatsApp />);

    await waitFor(() => expect(screen.getByTestId("sessao-banner")).toHaveTextContent("Aguardando pareamento"));
    expect(screen.getByTestId("sessao-banner")).toHaveTextContent("ação de operador");
  });

  it("renders the empty state when there are no groups", async () => {
    mockRoutes({ grupos: { items: [], total: 0 } });
    const { default: WhatsApp } = await import("../WhatsApp");
    renderPage(<WhatsApp />);

    await waitFor(() => expect(screen.getByText("Nenhum grupo cadastrado.")).toBeInTheDocument());
  });
});

describe("WhatsApp — invite link role gating (D3)", () => {
  it("admin: reveals the invite link on click, masks phones in the roster", async () => {
    mockUseAuthStore.mockReturnValue({ user: { user_metadata: { org_role: "admin" } } });
    mockRoutes();
    const { default: WhatsApp } = await import("../WhatsApp");
    renderPage(<WhatsApp />);

    await waitFor(() => expect(screen.getByTestId("grupo-row-g-1")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("grupo-row-g-1"));

    await waitFor(() => expect(screen.getByTestId("grupo-detail-dialog")).toBeInTheDocument());
    // Roster phone is masked to the last 4 digits, never the raw E.164 value.
    await waitFor(() => expect(screen.getByTestId("grupo-roster-item-m-1")).toBeInTheDocument());
    expect(screen.getByTestId("grupo-roster-item-m-1")).toHaveTextContent("1234");
    expect(screen.getByTestId("grupo-roster-item-m-1")).not.toHaveTextContent("+5511999991234");
    // The roster came off the SAME detail GET the drawer already makes —
    // no separate (never-built) `/membros` request (task 7 regression).
    expect(mockGet).not.toHaveBeenCalledWith(expect.stringContaining("/membros"));

    // Invite section exists for an admin.
    expect(screen.getByTestId("grupo-convite-section")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("grupo-convite-revelar"));
    await waitFor(() => expect(screen.getByTestId("grupo-convite-link")).toHaveTextContent("https://chat.whatsapp.com/abc123"));
  });

  it("moderador: the invite-link section is ABSENT from the DOM, not merely hidden", async () => {
    mockUseAuthStore.mockReturnValue({ user: { user_metadata: { org_role: "moderador" } } });
    mockRoutes();
    const { default: WhatsApp } = await import("../WhatsApp");
    renderPage(<WhatsApp />);

    // The "+ Novo grupo" admin-only affordance is also absent.
    await waitFor(() => expect(screen.getByTestId("grupo-row-g-1")).toBeInTheDocument());
    expect(screen.queryByTestId("whatsapp-novo-grupo")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("grupo-row-g-1"));
    await waitFor(() => expect(screen.getByTestId("grupo-detail-dialog")).toBeInTheDocument());
    expect(screen.queryByTestId("grupo-convite-section")).not.toBeInTheDocument();
    // The convite endpoint was never even called for a moderador session.
    expect(mockGet).not.toHaveBeenCalledWith(`/api/whatsapp/grupos/${GRUPO.id}/convite`);
  });
});

describe("WhatsApp — Conexões link banner (community-fe-apikeys-conexoes slice)", () => {
  it("admin: sees the honest banner + link to /whatsapp/conexoes", async () => {
    mockUseAuthStore.mockReturnValue({ user: { user_metadata: { org_role: "admin" } } });
    mockRoutes();
    const { default: WhatsApp } = await import("../WhatsApp");
    renderPage(<WhatsApp />);

    await waitFor(() => expect(screen.getByTestId("whatsapp-conexoes-link-banner")).toBeInTheDocument());
    expect(screen.getByTestId("whatsapp-conexoes-link-banner")).toHaveTextContent("Integração futura");
    fireEvent.click(screen.getByTestId("whatsapp-conexoes-link"));
    expect(mockNavigate).toHaveBeenCalledWith("/whatsapp/conexoes");
  });

  it("moderador: the Conexões link banner is ABSENT from the DOM, not merely hidden", async () => {
    mockUseAuthStore.mockReturnValue({ user: { user_metadata: { org_role: "moderador" } } });
    mockRoutes();
    const { default: WhatsApp } = await import("../WhatsApp");
    renderPage(<WhatsApp />);

    await waitFor(() => expect(screen.getByTestId("grupo-row-g-1")).toBeInTheDocument());
    expect(screen.queryByTestId("whatsapp-conexoes-link-banner")).not.toBeInTheDocument();
  });
});

describe("WhatsApp — errors", () => {
  it("renders the server's detail verbatim on a groups-list failure", async () => {
    const { ApiError } = await import("@noctusai/lib");
    mockGet.mockImplementation((path: string) => {
      if (path === "/api/whatsapp/sessao") return Promise.resolve({ estado: "WORKING", sessao: "default" });
      if (path === "/api/whatsapp/grupos") return Promise.reject(new ApiError(500, "Erro interno."));
      return Promise.reject(new Error("unexpected"));
    });
    const { default: WhatsApp } = await import("../WhatsApp");
    renderPage(<WhatsApp />);

    await waitFor(() => expect(screen.getByText("Erro interno.")).toBeInTheDocument());
  });
});
