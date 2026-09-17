/**
 * Conexões WhatsApp page render tests (community-fe-apikeys-conexoes
 * slice).
 *
 * Proves:
 * 1. A non-admin sees the "restrita a administradores" message — the
 *    `<WhatsAppConnectionsPage/>` subtree never mounts.
 * 2. An admin sees `<WhatsAppConnectionsPage/>` (`@noctusai/lib/components`)
 *    mounted against `/api/whatsapp/connections`, with the honest
 *    "integração futura" banner + matching empty-state copy — WhatsApp is
 *    NOT connected through this page yet (2026-09-17 user decision).
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

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function renderPage(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGet.mockResolvedValue([]);
});

describe("WhatsApp Conexoes", () => {
  it("mostra a mensagem de acesso restrito para quem não é admin", async () => {
    mockUseAuthStore.mockReturnValue({ user: { user_metadata: { org_role: "moderador" } } });
    const Conexoes = (await import("../Conexoes")).default;
    renderPage(<Conexoes />);

    expect(screen.getByTestId("conexoes-acesso-restrito")).toBeInTheDocument();
    expect(screen.getByText(/restrita a administradores/i)).toBeInTheDocument();
    expect(screen.queryByTestId("whatsapp-connections-page")).not.toBeInTheDocument();
    expect(mockGet).not.toHaveBeenCalled();
  });

  it("monta o WhatsAppConnectionsPage com o banner honesto para um admin", async () => {
    mockUseAuthStore.mockReturnValue({ user: { user_metadata: { org_role: "admin" } } });
    const Conexoes = (await import("../Conexoes")).default;
    renderPage(<Conexoes />);

    await waitFor(() => expect(screen.getByTestId("whatsapp-connections-page")).toBeInTheDocument());
    expect(mockGet).toHaveBeenCalledWith("/api/whatsapp/connections");
    expect(screen.getByTestId("wa-conexoes-future-work-banner")).toHaveTextContent(
      "Integração futura — o WhatsApp ainda não está conectado a este produto. A conexão será feita numa próxima etapa.",
    );
    expect(screen.queryByTestId("conexoes-acesso-restrito")).not.toBeInTheDocument();
  });

  it("mostra o empty-state honesto quando não há conexões", async () => {
    mockUseAuthStore.mockReturnValue({ user: { user_metadata: { org_role: "admin" } } });
    const Conexoes = (await import("../Conexoes")).default;
    renderPage(<Conexoes />);

    await waitFor(() => expect(screen.getByTestId("wa-empty-state")).toBeInTheDocument());
    expect(screen.getByTestId("wa-conexoes-empty-state")).toHaveTextContent(
      "Integração futura — o WhatsApp ainda não está conectado a este produto. A conexão será feita numa próxima etapa.",
    );
  });
});
