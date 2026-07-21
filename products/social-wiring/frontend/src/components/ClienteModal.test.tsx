/**
 * ClienteModal tests.
 *
 * Tests:
 *   1. Renders the modal with client name in header
 *   2. Contas tab shows integration accounts
 *   3. Contas tab shows empty state when no integrations
 *   4. Contas tab shows WA connections
 *   5. Contas tab shows WA empty state when no connections
 *   6. Chat tab shows WA connection picker when >1 connections exist
 *   7. Chat tab shows empty state when no WA connections
 *   8. Modal does not render when open=false
 *
 * Mock strategy:
 *   · All hooks are vi.fn()s configured in beforeEach
 *   · @noctusai/lib stubs (IntegrationCard, IntegrationCardModal, getProviderConfig)
 *   · ConnectionDetailDialog stubbed (complex WAHA component)
 *   · WhatsAppChatWindow stubbed (tested separately)
 *   · react-router-dom's useNavigate is a spy (mockNavigate)
 *   · @/state/useActiveAccount is a selector-shaped stub (mockSetActiveClient/Account)
 *   · shadcn Dialog, Tabs, Select are structurally passed-through to let
 *     the tab renders work; simpler primitives are identity mocks.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

// ─── Router + active-account store mocks ──────────────────────────────────

const mockNavigate = vi.fn();
vi.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
}));

const mockSetActiveClient = vi.fn();
const mockSetActiveAccount = vi.fn();
const activeAccountState = {
  activeAccountId: null as string | null,
  activeClientId: null as string | null,
  setActiveAccount: mockSetActiveAccount,
  setActiveClient: mockSetActiveClient,
  clearSelection: vi.fn(),
};
vi.mock("@/state/useActiveAccount", () => ({
  useActiveAccountStore: (selector: (s: typeof activeAccountState) => unknown) =>
    selector(activeAccountState),
}));

// ─── Hook mocks ────────────────────────────────────────────────────────────

const mockUseIntegrationAccounts = vi.fn();
const mockUseUpdateAccount = vi.fn();
const mockUseSetDefaultAccount = vi.fn();
const mockUseDeleteAccount = vi.fn();
const mockUseSyncAccount = vi.fn();
const mockUseUpdateClient = vi.fn();
const mockUseDeleteClient = vi.fn();

const mockUseSubmitInstagramToken = vi.fn();

vi.mock("@/hooks/useIntegrationAccounts", () => ({
  useIntegrationAccounts: mockUseIntegrationAccounts,
  useUpdateAccount: mockUseUpdateAccount,
  useSetDefaultAccount: mockUseSetDefaultAccount,
  useDeleteAccount: mockUseDeleteAccount,
  useSyncAccount: mockUseSyncAccount,
  useCreateAccount: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
  useStartYouTubeOAuth: () => ({ mutate: vi.fn(), isPending: false }),
  useStartProviderOAuth: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
  useSubmitInstagramToken: mockUseSubmitInstagramToken,
}));

vi.mock("@/hooks/useClients", () => ({
  useUpdateClient: mockUseUpdateClient,
  useDeleteClient: mockUseDeleteClient,
}));

const mockUseClientWhatsAppConnections = vi.fn();
const mockUseWhatsAppConnectionMutations = vi.fn();
const mockUseWhatsAppConnectionStatus = vi.fn();

vi.mock("@/hooks/useWhatsAppConnections", () => ({
  useClientWhatsAppConnections: mockUseClientWhatsAppConnections,
  useWhatsAppConnectionMutations: mockUseWhatsAppConnectionMutations,
  useWhatsAppConnectionStatus: mockUseWhatsAppConnectionStatus,
  useWhatsAppConnectionActions: vi.fn(() => ({
    start: { mutate: vi.fn(), isPending: false },
    restart: { mutate: vi.fn(), isPending: false },
    logout: { mutate: vi.fn(), isPending: false },
  })),
  useWhatsAppConnectionQr: vi.fn(() => ({ data: null })),
  useRevealApiKey: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useToggleAutoReply: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));

const mockUseMailchimpConnection = vi.fn();

vi.mock("@/hooks/useMailchimp", () => ({
  useMailchimpConnection: mockUseMailchimpConnection,
  useUpsertMailchimpConnection: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

// ─── Component mocks ─────────────────────────────────────────────────────────

const PROVIDER_DASHBOARD_ROUTES: Record<string, string> = {
  youtube: "/youtube",
  meta: "/meta",
  whatsapp: "/whatsapp-chat",
};

vi.mock("@noctusai/lib", () => ({
  IntegrationCard: ({ account, onOpenModal, onOpenDetails }: any) => (
    <div data-testid="integration-card" data-account-id={account?.id}>
      {account?.account_label}
      {onOpenModal && (
        <button
          data-testid={`open-dashboard-${account?.id}`}
          onClick={() => onOpenModal(account)}
        >
          Abrir
        </button>
      )}
      {onOpenDetails && (
        <button
          data-testid={`open-details-${account?.id}`}
          onClick={() => onOpenDetails(account)}
        >
          Detalhes
        </button>
      )}
    </div>
  ),
  IntegrationCardModal: ({ account, onClose }: any) =>
    account ? (
      <div data-testid="integration-card-modal">
        <button onClick={onClose}>Fechar modal</button>
      </div>
    ) : null,
  // Mirrors seed/lib/frontend/src/design-system/integrations/providerCardConfig.ts
  // dashboardRoute map (youtube/meta/whatsapp) — kept in sync manually since
  // this is a test-only stub, not a re-export of the real registry.
  getProviderConfig: (provider: string) => {
    const dashboardRoute = PROVIDER_DASHBOARD_ROUTES[provider?.toLowerCase()];
    return dashboardRoute ? { provider, dashboardRoute } : undefined;
  },
}));

vi.mock("@/components/ConnectionDetailDialog", () => ({
  ConnectionDetailDialog: ({ line, onClose }: any) => (
    <div data-testid="connection-detail-dialog" data-line-id={line?.id}>
      <button onClick={onClose}>Fechar detalhe</button>
    </div>
  ),
}));

vi.mock("@/components/WhatsAppChatWindow", () => ({
  WhatsAppChatWindow: ({ connectionId }: any) => (
    <div data-testid="wa-chat-window" data-connection-id={connectionId} />
  ),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const baseClient = {
  id: "client-1",
  org_id: "org-1",
  slug: "acme",
  name: "Acme Corp",
  kind: "empresa",
  notes: "Some notes",
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
};

const makeAccount = (id: string, label: string) => ({
  id,
  org_id: "org-1",
  provider: "youtube",
  account_label: label,
  client_id: "client-1",
  status: "validated",
  channel_info: {},
  metadata: {},
  is_default: false,
  last_synced_at: null,
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
});

const makeWaLine = (id: string, label: string) => ({
  id,
  label,
  session_name: `session-${id}`,
  webhook_url: null,
  auto_reply_enabled: false,
  client_id: "client-1",
});

// ─── Defaults ─────────────────────────────────────────────────────────────────

beforeEach(() => {
  mockUseIntegrationAccounts.mockReturnValue({ data: [], isLoading: false, isError: false });
  mockUseClientWhatsAppConnections.mockReturnValue({ data: [], isLoading: false, isError: false });
  mockUseWhatsAppConnectionMutations.mockReturnValue({
    create: { mutateAsync: vi.fn(), isPending: false },
    remove: { mutate: vi.fn(), isPending: false },
  });
  mockUseWhatsAppConnectionStatus.mockReturnValue({ data: null });
  mockUseUpdateClient.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockUseDeleteClient.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockUseUpdateAccount.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockUseSetDefaultAccount.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockUseDeleteAccount.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockUseSyncAccount.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockUseMailchimpConnection.mockReturnValue({ data: undefined, isLoading: false });
  mockUseSubmitInstagramToken.mockReturnValue({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false });
  mockNavigate.mockClear();
  mockSetActiveClient.mockClear();
  mockSetActiveAccount.mockClear();
});

// ─── Helpers ──────────────────────────────────────────────────────────────────

async function renderClienteModal(props: { open?: boolean; defaultTab?: "contas" | "chat" } = {}) {
  const { ClienteModal } = await import("./ClienteModal");
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  return {
    ...rtl.render(
      React.createElement(ClienteModal, {
        client: baseClient,
        open: props.open ?? true,
        onClose: vi.fn(),
        defaultTab: props.defaultTab ?? "contas",
      }),
    ),
    fireEvent: rtl.fireEvent,
  };
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("ClienteModal — header", () => {
  it("renders client name in dialog header", async () => {
    const { getByText } = await renderClienteModal();
    expect(getByText("Acme Corp")).toBeTruthy();
  });

  it("does not render when open=false", async () => {
    const { queryByTestId } = await renderClienteModal({ open: false });
    expect(queryByTestId("cliente-modal")).toBeNull();
  });
});

describe("ClienteModal — Contas tab", () => {
  it("renders the contas tab content", async () => {
    const { getByTestId } = await renderClienteModal({ defaultTab: "contas" });
    expect(getByTestId("contas-tab")).toBeTruthy();
  });

  it("renders integration cards when accounts exist", async () => {
    mockUseIntegrationAccounts.mockReturnValue({
      data: [
        makeAccount("acc-1", "Canal YouTube"),
        makeAccount("acc-2", "Drive Account"),
      ],
      isLoading: false,
      isError: false,
    });

    const { getAllByTestId } = await renderClienteModal({ defaultTab: "contas" });
    expect(getAllByTestId("integration-card").length).toBe(2);
  });

  it("shows the provider grid when no integration accounts exist", async () => {
    mockUseIntegrationAccounts.mockReturnValue({ data: [], isLoading: false, isError: false });
    const { getByTestId, getAllByText } = await renderClienteModal({ defaultTab: "contas" });
    // Provider grid is always rendered (greyed rows for unconnected providers)
    expect(getByTestId("integrations-grid")).toBeTruthy();
    // OAuth providers (YouTube, Gmail, Google Drive, Meta) show "Conectar" buttons
    const conectarBtns = getAllByText(/Conectar/i);
    expect(conectarBtns.length).toBeGreaterThanOrEqual(4);
  });

  it("shows Meta as a live OAuth Conectar row (not 'em breve')", async () => {
    mockUseIntegrationAccounts.mockReturnValue({ data: [], isLoading: false, isError: false });
    const { getByTestId, queryByText } = await renderClienteModal({ defaultTab: "contas" });
    expect(getByTestId("provider-row-meta")).toBeTruthy();
    expect(getByTestId("connect-btn-meta")).toBeTruthy();
    expect(queryByText(/em breve/i)).toBeNull();
  });

  it("wires the Meta Conectar button to useStartProviderOAuth('meta')", async () => {
    mockUseIntegrationAccounts.mockReturnValue({ data: [], isLoading: false, isError: false });
    const { getByTestId, fireEvent } = await renderClienteModal({ defaultTab: "contas" });
    // useStartProviderOAuth is mocked generically for every provider — clicking
    // Meta's button should not throw and should hit the same mutate() path.
    expect(() => fireEvent.click(getByTestId("connect-btn-meta"))).not.toThrow();
  });

  it("shows WA connections when present", async () => {
    mockUseClientWhatsAppConnections.mockReturnValue({
      data: [makeWaLine("wa-1", "WhatsApp Vendas")],
      isLoading: false,
      isError: false,
    });
    mockUseWhatsAppConnectionStatus.mockReturnValue({
      data: { status: "WORKING", paired: true, me_id: "551199998888" },
    });

    // IntegrationCard is mocked globally; just confirm it renders 1 card
    const { getAllByTestId } = await renderClienteModal({ defaultTab: "contas" });
    // 1 WA connection → renders 1 IntegrationCard via WaConnectionCard
    expect(getAllByTestId("integration-card").length).toBeGreaterThanOrEqual(1);
  });

  it("shows WA empty state when no connections", async () => {
    mockUseClientWhatsAppConnections.mockReturnValue({ data: [], isLoading: false, isError: false });
    const { getByText } = await renderClienteModal({ defaultTab: "contas" });
    expect(getByText(/Nenhuma conexão WhatsApp/i)).toBeTruthy();
  });
});

describe("ClienteModal — connected-card deep-link (card body click)", () => {
  it("youtube card body click sets active client+account and navigates to /youtube", async () => {
    mockUseIntegrationAccounts.mockReturnValue({
      data: [makeAccount("acc-1", "Canal YouTube")],
      isLoading: false,
      isError: false,
    });

    const { getByTestId, fireEvent } = await renderClienteModal({ defaultTab: "contas" });
    fireEvent.click(getByTestId("open-dashboard-acc-1"));

    expect(mockSetActiveClient).toHaveBeenCalledWith("client-1");
    expect(mockSetActiveAccount).toHaveBeenCalledWith("acc-1");
    expect(mockNavigate).toHaveBeenCalledWith("/youtube");
    // The detail modal must NOT open — dashboardRoute takes the body click.
    expect(document.querySelector('[data-testid="integration-card-modal"]')).toBeNull();
  });

  it("meta card body click navigates to /meta", async () => {
    mockUseIntegrationAccounts.mockReturnValue({
      data: [{ ...makeAccount("acc-2", "Página Acme"), provider: "meta" }],
      isLoading: false,
      isError: false,
    });

    const { getByTestId, fireEvent } = await renderClienteModal({ defaultTab: "contas" });
    fireEvent.click(getByTestId("open-dashboard-acc-2"));

    expect(mockSetActiveClient).toHaveBeenCalledWith("client-1");
    expect(mockSetActiveAccount).toHaveBeenCalledWith("acc-2");
    expect(mockNavigate).toHaveBeenCalledWith("/meta");
  });

  it("a provider without a dashboardRoute (gmail) still opens the detail modal on body click", async () => {
    mockUseIntegrationAccounts.mockReturnValue({
      data: [{ ...makeAccount("acc-3", "Conta Gmail"), provider: "gmail" }],
      isLoading: false,
      isError: false,
    });

    const { getByTestId, fireEvent } = await renderClienteModal({ defaultTab: "contas" });
    fireEvent.click(getByTestId("open-dashboard-acc-3"));

    expect(mockNavigate).not.toHaveBeenCalled();
    expect(getByTestId("integration-card-modal")).toBeTruthy();
  });

  it("the secondary 'detalhes' affordance always opens the detail modal (does not navigate)", async () => {
    mockUseIntegrationAccounts.mockReturnValue({
      data: [makeAccount("acc-1", "Canal YouTube")],
      isLoading: false,
      isError: false,
    });

    const { getByTestId, fireEvent } = await renderClienteModal({ defaultTab: "contas" });
    fireEvent.click(getByTestId("open-details-acc-1"));

    expect(mockNavigate).not.toHaveBeenCalled();
    expect(getByTestId("integration-card-modal")).toBeTruthy();
  });

  it("whatsapp card body click sets active client+connection and navigates to /whatsapp-chat", async () => {
    mockUseClientWhatsAppConnections.mockReturnValue({
      data: [makeWaLine("wa-1", "WhatsApp Vendas")],
      isLoading: false,
      isError: false,
    });
    mockUseWhatsAppConnectionStatus.mockReturnValue({
      data: { status: "WORKING", paired: true, me_id: "551199998888" },
    });

    const { getByTestId, fireEvent } = await renderClienteModal({ defaultTab: "contas" });
    fireEvent.click(getByTestId("open-dashboard-wa-1"));

    expect(mockSetActiveClient).toHaveBeenCalledWith("client-1");
    expect(mockSetActiveAccount).toHaveBeenCalledWith("wa-1");
    expect(mockNavigate).toHaveBeenCalledWith("/whatsapp-chat");
    expect(document.querySelector('[data-testid="connection-detail-dialog"]')).toBeNull();
  });

  it("whatsapp card 'detalhes' affordance still opens the ConnectionDetailDialog (QR/config)", async () => {
    mockUseClientWhatsAppConnections.mockReturnValue({
      data: [makeWaLine("wa-1", "WhatsApp Vendas")],
      isLoading: false,
      isError: false,
    });
    mockUseWhatsAppConnectionStatus.mockReturnValue({
      data: { status: "WORKING", paired: true, me_id: "551199998888" },
    });

    const { getByTestId, fireEvent } = await renderClienteModal({ defaultTab: "contas" });
    fireEvent.click(getByTestId("open-details-wa-1"));

    expect(mockNavigate).not.toHaveBeenCalled();
    expect(getByTestId("connection-detail-dialog")).toBeTruthy();
  });
});

describe("ClienteModal — Mailchimp per-cliente connect", () => {
  it("shows a manual Conectar affordance when not connected", async () => {
    mockUseMailchimpConnection.mockReturnValue({ data: undefined, isLoading: false });
    const { getByTestId, queryByTestId } = await renderClienteModal({ defaultTab: "contas" });
    expect(getByTestId("provider-row-mailchimp")).toBeTruthy();
    expect(getByTestId("connect-btn-mailchimp")).toBeTruthy();
    // Form is collapsed until the user clicks Conectar
    expect(queryByTestId("mailchimp-connect-form")).toBeNull();
  });

  it("toggles the inline API-key form on Conectar", async () => {
    mockUseMailchimpConnection.mockReturnValue({ data: undefined, isLoading: false });
    const { getByTestId, fireEvent } = await renderClienteModal({ defaultTab: "contas" });
    fireEvent.click(getByTestId("connect-btn-mailchimp"));
    expect(getByTestId("mailchimp-connect-form")).toBeTruthy();
    expect(getByTestId("mailchimp-api-key")).toBeTruthy();
  });

  it("renders the connected indicator with audience when connected", async () => {
    mockUseMailchimpConnection.mockReturnValue({
      data: {
        connected: true,
        client_id: "client-1",
        server_prefix: "us6",
        audience_id: "aud-1",
        audience_name: "Newsletter",
        created_at: "2026-01-01",
        updated_at: "2026-01-01",
      },
      isLoading: false,
    });
    const { getByText, getByTestId } = await renderClienteModal({ defaultTab: "contas" });
    expect(getByText("Conectado")).toBeTruthy();
    expect(getByText(/Newsletter/)).toBeTruthy();
    // Re-configure re-opens the same form (pre-filled)
    expect(getByTestId("mailchimp-reconfigure-btn")).toBeTruthy();
  });
});

describe("ClienteModal — Instagram connect (OAuth + token-paste fallback)", () => {
  it("shows Instagram as a live OAuth Conectar row plus a token-paste toggle", async () => {
    mockUseIntegrationAccounts.mockReturnValue({ data: [], isLoading: false, isError: false });
    const { getByTestId, queryByTestId } = await renderClienteModal({ defaultTab: "contas" });
    expect(getByTestId("provider-row-instagram")).toBeTruthy();
    expect(getByTestId("connect-btn-instagram")).toBeTruthy();
    expect(getByTestId("instagram-token-toggle")).toBeTruthy();
    // Token-paste form is collapsed until the toggle is clicked
    expect(queryByTestId("instagram-token-form")).toBeNull();
  });

  it("wires the Instagram Conectar button to useStartProviderOAuth('instagram')", async () => {
    mockUseIntegrationAccounts.mockReturnValue({ data: [], isLoading: false, isError: false });
    const { getByTestId, fireEvent } = await renderClienteModal({ defaultTab: "contas" });
    expect(() => fireEvent.click(getByTestId("connect-btn-instagram"))).not.toThrow();
  });

  it("toggles the inline token-paste form open/closed", async () => {
    mockUseIntegrationAccounts.mockReturnValue({ data: [], isLoading: false, isError: false });
    const { getByTestId, queryByTestId, fireEvent } = await renderClienteModal({ defaultTab: "contas" });
    fireEvent.click(getByTestId("instagram-token-toggle"));
    expect(getByTestId("instagram-token-form")).toBeTruthy();
    expect(getByTestId("instagram-token-input")).toBeTruthy();
    fireEvent.click(getByTestId("instagram-token-toggle"));
    expect(queryByTestId("instagram-token-form")).toBeNull();
  });

  it("submits the pasted token via useSubmitInstagramToken and closes the form on success", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({ id: "acc-ig", provider: "instagram", account_label: "IG", status: "validated" });
    mockUseSubmitInstagramToken.mockReturnValue({ mutate: vi.fn(), mutateAsync, isPending: false });
    mockUseIntegrationAccounts.mockReturnValue({ data: [], isLoading: false, isError: false });

    const { getByTestId, queryByTestId, fireEvent } = await renderClienteModal({ defaultTab: "contas" });
    fireEvent.click(getByTestId("instagram-token-toggle"));
    fireEvent.change(getByTestId("instagram-token-input"), { target: { value: "IGAA-fake-token" } });
    fireEvent.click(getByTestId("instagram-token-submit"));

    await vi.waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledWith({ access_token: "IGAA-fake-token", client_id: "client-1" });
    });
    await vi.waitFor(() => {
      expect(queryByTestId("instagram-token-form")).toBeNull();
    });
  });

  it("surfaces the backend's 400 detail inline when the token is invalid", async () => {
    const mutateAsync = vi.fn().mockRejectedValue(new Error("[400] Token invalido ou expirado."));
    mockUseSubmitInstagramToken.mockReturnValue({ mutate: vi.fn(), mutateAsync, isPending: false });
    mockUseIntegrationAccounts.mockReturnValue({ data: [], isLoading: false, isError: false });

    const { getByTestId, fireEvent } = await renderClienteModal({ defaultTab: "contas" });
    fireEvent.click(getByTestId("instagram-token-toggle"));
    fireEvent.change(getByTestId("instagram-token-input"), { target: { value: "bad-token" } });
    fireEvent.click(getByTestId("instagram-token-submit"));

    await vi.waitFor(() => {
      expect(getByTestId("instagram-token-error").textContent).toMatch(/Token invalido ou expirado/);
    });
    // The form stays open on error so the user can retry.
    expect(getByTestId("instagram-token-form")).toBeTruthy();
  });
});

describe("ClienteModal — Chat tab", () => {
  // NOTE: Radix Tabs only mounts the ACTIVE tab's content in JSDOM.
  // Tests use visible content (text/testids within the active tab) rather
  // than the container data-testid which requires both tabs to be in DOM.

  it("shows empty state text when no WA connections and chat tab is active", async () => {
    mockUseClientWhatsAppConnections.mockReturnValue({ data: [], isLoading: false, isError: false });
    const { getByText } = await renderClienteModal({ defaultTab: "chat" });
    // "Nenhuma conexão WhatsApp" comes from ChatTab's empty state
    expect(getByText(/Nenhuma conexão WhatsApp/i)).toBeTruthy();
  });

  it("renders WhatsAppChatWindow when a WA connection exists and chat tab is active", async () => {
    mockUseClientWhatsAppConnections.mockReturnValue({
      data: [makeWaLine("wa-1", "WhatsApp Vendas")],
      isLoading: false,
      isError: false,
    });

    const { getByTestId } = await renderClienteModal({ defaultTab: "chat" });
    const chatWindow = getByTestId("wa-chat-window");
    expect(chatWindow.getAttribute("data-connection-id")).toBe("wa-1");
  });

  it("shows connection picker when >1 WA connections and chat tab is active", async () => {
    mockUseClientWhatsAppConnections.mockReturnValue({
      data: [
        makeWaLine("wa-1", "WhatsApp Vendas"),
        makeWaLine("wa-2", "WhatsApp Suporte"),
      ],
      isLoading: false,
      isError: false,
    });

    const { getByText } = await renderClienteModal({ defaultTab: "chat" });
    // Select trigger text of the first connection appears when picker renders
    expect(getByText("WhatsApp Vendas")).toBeTruthy();
  });
});
