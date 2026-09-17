/**
 * Configurações page render tests (community-fe-apikeys-conexoes slice).
 *
 * Proves:
 * 1. A non-admin sees the "restrita a administradores" message — the
 *    `<ApiKeysPanel/>` subtree never mounts (genuinely absent, not CSS).
 * 2. An admin sees `<ApiKeysPanel/>` (`@noctusai/lib/components`) mounted
 *    and fed by `createApiKeysHooks` against `/api/settings/api-keys`,
 *    rendering the real keys the (fake) API returns.
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

const API_KEYS_STATUS = {
  items: [
    {
      key: "stripe_secret_key",
      label: "Chave secreta do Stripe",
      description: "Usada para criar sessões de checkout.",
      is_secret: true,
      testable: true,
      input_type: "password",
      placeholder: "sk_live_...",
      configured: true,
      options: [],
      default: null,
      hint: "...b3f9",
      source: "local",
      updated_at: "2026-09-01T00:00:00Z",
    },
    {
      key: "asaas_api_key",
      label: "Chave da API do Asaas",
      description: "Usada para criar cobranças.",
      is_secret: true,
      testable: false,
      input_type: "password",
      placeholder: "",
      configured: false,
      options: [],
      default: null,
      hint: null,
      source: null,
      updated_at: null,
    },
  ],
  total: 2,
};

beforeEach(() => {
  vi.clearAllMocks();
  mockGet.mockResolvedValue(API_KEYS_STATUS);
});

describe("Configuracoes", () => {
  it("mostra a mensagem de acesso restrito para quem não é admin", async () => {
    mockUseAuthStore.mockReturnValue({ user: { user_metadata: { org_role: "member" } } });
    const Configuracoes = (await import("../Configuracoes")).default;
    renderPage(<Configuracoes />);

    expect(screen.getByTestId("configuracoes-acesso-restrito")).toBeInTheDocument();
    expect(screen.getByText(/restrita a administradores/i)).toBeInTheDocument();
    expect(screen.queryByTestId("api-keys-panel")).not.toBeInTheDocument();
    expect(mockGet).not.toHaveBeenCalled();
  });

  it("monta o ApiKeysPanel com as chaves reais para um admin", async () => {
    mockUseAuthStore.mockReturnValue({ user: { user_metadata: { org_role: "admin" } } });
    const Configuracoes = (await import("../Configuracoes")).default;
    renderPage(<Configuracoes />);

    await waitFor(() => expect(screen.getByText("Chave secreta do Stripe")).toBeInTheDocument());
    expect(mockGet).toHaveBeenCalledWith("/api/settings/api-keys");
    expect(screen.getByText("Chave da API do Asaas")).toBeInTheDocument();
    expect(screen.queryByTestId("configuracoes-acesso-restrito")).not.toBeInTheDocument();
  });

  it("também libera para o dono (owner) da organização", async () => {
    mockUseAuthStore.mockReturnValue({ user: { user_metadata: { org_role: "owner" } } });
    const Configuracoes = (await import("../Configuracoes")).default;
    renderPage(<Configuracoes />);

    await waitFor(() => expect(screen.getByTestId("api-keys-panel")).toBeInTheDocument());
  });
});
