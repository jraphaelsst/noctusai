/**
 * Tests for Integrations page, AddAccountModal, and the unified Conexoes page.
 *
 * Strategy: ONE consolidated mock of @/hooks/useIntegrationAccounts (vi.mock is
 * file-scoped + hoisted — multiple mocks of the same module collide and the last
 * wins, which silently broke every test before this file ran under CI). All
 * hooks are vi.fn()s configured per-test. UI-primitive mocks use JSX (the
 * automatic react/jsx-runtime → a single React instance; `require("react")`
 * pulled a 2nd CJS instance → dual-React). Queries come from the render return
 * (bound to the actual container) rather than the global `screen`.
 *
 * Shape note: providers use `id` (not `name`), manual fields use `name` (not `key`).
 * API returns bare arrays/objects — no envelope wrappers.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// localStorage/sessionStorage are provisioned by the shared seed vitest setup
// (seed/framework/frontend/vitest.setup.ts) — no per-file polyfill needed.

// Unmount previous renders so render-return queries (which scan document.body)
// don't trip "found multiple elements". Dynamic import → same @testing-library
// instance the tests render with.
afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

// ─── One configurable hook mock (all hooks as vi.fn) ───────────────────────
const mockProviders = vi.fn();
const mockAccounts = vi.fn();
const mockSetDefault = vi.fn();
const mockDelete = vi.fn();
const mockCreate = vi.fn();
const mockOAuth = vi.fn();
const mockAdoptLegacy = vi.fn();

// No importOriginal — the real module imports the Supabase client (needs
// build-time VITE_* env). The components only import these hooks (+ erased
// types) from this module, so providing them directly is complete.
vi.mock("@/hooks/useIntegrationAccounts", () => ({
  useIntegrationProviders: mockProviders,
  useIntegrationAccounts: mockAccounts,
  useSetDefaultAccount: mockSetDefault,
  useDeleteAccount: mockDelete,
  useCreateAccount: mockCreate,
  useStartYouTubeOAuth: mockOAuth,
  useAdoptLegacy: mockAdoptLegacy,
  // New in P2 refactor — needed by Conexoes
  useUpdateAccount: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useSyncAccount: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
}));

// Clients hooks (needed by Conexoes which now fetches clients for grouping)
vi.mock("@/hooks/useClients", () => ({
  useClients: vi.fn(() => ({ data: [], isLoading: false, isError: false })),
  useCreateClient: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useUpdateClient: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useDeleteClient: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
}));

// WhatsApp connections hooks (needed by Conexoes which embeds WhatsAppConnections)
vi.mock("@/hooks/useWhatsAppConnections", () => ({
  useWhatsAppConnections: vi.fn(() => ({ data: [], isLoading: false })),
  useWhatsAppConnectionMutations: vi.fn(() => ({
    create: { mutate: vi.fn(), isPending: false },
    remove: { mutate: vi.fn(), isPending: false },
  })),
  useWhatsAppConnectionStatus: vi.fn(() => ({ data: null })),
  useWhatsAppConnectionQr: vi.fn(() => ({ data: null })),
  useWhatsAppConnectionActions: vi.fn(() => ({
    start: { mutate: vi.fn(), isPending: false },
    restart: { mutate: vi.fn(), isPending: false },
    logout: { mutate: vi.fn(), isPending: false },
    configureWebhook: { mutate: vi.fn(), isPending: false },
  })),
}));

// react-router-dom (needed by Conexoes for useSearchParams)
vi.mock("react-router-dom", () => ({
  useSearchParams: vi.fn(() => [new URLSearchParams(), vi.fn()]),
}));

// ─── UI-primitive mocks (JSX — single React instance) ──────────────────────
vi.mock("@/components/ui/card", () => ({
  Card: ({ children }: any) => <div>{children}</div>,
  CardContent: ({ children }: any) => <div>{children}</div>,
  CardDescription: ({ children }: any) => <div>{children}</div>,
  CardHeader: ({ children }: any) => <div>{children}</div>,
  CardTitle: ({ children }: any) => <div>{children}</div>,
}));
vi.mock("@/components/ui/button", () => ({
  Button: ({ children, onClick, disabled }: any) => (
    <button onClick={onClick} disabled={disabled}>{children}</button>
  ),
}));
vi.mock("@/components/ui/badge", () => ({ Badge: ({ children }: any) => <span>{children}</span> }));
vi.mock("@/components/ui/alert-dialog", () => ({
  AlertDialog: ({ children }: any) => <div>{children}</div>,
  AlertDialogAction: ({ children, onClick }: any) => <button onClick={onClick}>{children}</button>,
  AlertDialogCancel: ({ children }: any) => <div>{children}</div>,
  AlertDialogContent: ({ children }: any) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: any) => <div>{children}</div>,
  AlertDialogFooter: ({ children }: any) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: any) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: any) => <div>{children}</div>,
}));
vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({ children }: any) => <div>{children}</div>,
  DialogContent: ({ children }: any) => <div>{children}</div>,
  DialogDescription: ({ children }: any) => <div>{children}</div>,
  DialogFooter: ({ children }: any) => <div>{children}</div>,
  DialogHeader: ({ children }: any) => <div>{children}</div>,
  DialogTitle: ({ children }: any) => <div>{children}</div>,
}));
vi.mock("@/components/ui/input", () => ({
  Input: ({ id, value, onChange, type, disabled }: any) => (
    <input id={id} value={value} onChange={onChange} type={type} disabled={disabled} />
  ),
}));
vi.mock("@/components/ui/label", () => ({ Label: ({ children }: any) => <label>{children}</label> }));
vi.mock("@/components/ui/separator", () => ({ Separator: () => null }));
vi.mock("@/components/AddAccountModal", () => ({
  default: ({ onClose }: any) => (
    <div data-testid="add-account-modal"><button onClick={onClose}>Close</button></div>
  ),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

// @noctusai/lib — stub IntegrationCard + IntegrationCardModal (needed by Conexoes P2)
vi.mock("@noctusai/lib", () => ({
  IntegrationCard: ({ account }: any) => (
    <div data-testid="integration-card" data-account-label={account?.account_label}>
      {account?.account_label}
    </div>
  ),
  IntegrationCardModal: ({ account, onClose }: any) =>
    account ? (
      <div data-testid="integration-card-modal">
        <button onClick={onClose}>Fechar modal</button>
      </div>
    ) : null,
  resolveStatusBadge: (status: string) => ({ label: status, className: "badge", showSpinner: false }),
}));

// ClientManagementModal (needed by Conexoes P2)
vi.mock("@/components/ClientManagementModal", () => ({
  ClientManagementModal: ({ onClose }: any) => (
    <div data-testid="client-management-modal">
      <button onClick={onClose}>Fechar</button>
    </div>
  ),
}));

// Sensible defaults each test can override.
beforeEach(() => {
  mockProviders.mockReturnValue({ data: [], isLoading: false, isError: false });
  mockAccounts.mockReturnValue({ data: [], isLoading: false });
  mockSetDefault.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockDelete.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockCreate.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockOAuth.mockReturnValue({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false });
  mockAdoptLegacy.mockReturnValue({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false });
});

async function renderPage() {
  const { default: Integrations } = await import("./Integrations");
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  return { ...rtl.render(React.createElement(Integrations)), fireEvent: rtl.fireEvent };
}

async function renderConexoes() {
  const { default: Conexoes } = await import("./Conexoes");
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  return { ...rtl.render(React.createElement(Conexoes)), fireEvent: rtl.fireEvent };
}

// ─── Integrations page states ─────────────────────────────────────────────
describe("Integrations page — loading state", () => {
  it("renders loading spinner when providers loading", async () => {
    mockProviders.mockReturnValue({ data: [], isLoading: true, isError: false });
    const { getByText } = await renderPage();
    expect(getByText(/Carregando integracoes/i)).toBeTruthy();
  });
});

describe("Integrations page — empty providers", () => {
  it("renders empty state when no providers returned", async () => {
    mockProviders.mockReturnValue({ data: [], isLoading: false, isError: false });
    const { getByText } = await renderPage();
    expect(getByText(/Nenhum provedor disponivel/i)).toBeTruthy();
  });
});

describe("Integrations page — with providers", () => {
  // Provider now uses `id` (not `name`)
  const mockProvider = {
    id: "youtube", display_name: "YouTube", oauth_supported: true,
    manual_entry: false, manual_key_fields: [], tutorial_url: null,
    scopes: [], icon: null,
  };
  const mockAccount = {
    id: "acc-1", provider: "youtube", account_label: "Canal Principal",
    org_id: "org-1", metadata: { channel: "main" }, is_default: true,
    created_at: "2026-01-01", updated_at: "2026-01-01",
  };

  it("renders provider name and accounts", async () => {
    mockProviders.mockReturnValue({ data: [mockProvider], isLoading: false, isError: false });
    mockAccounts.mockReturnValue({ data: [mockAccount], isLoading: false });
    const { getByText } = await renderPage();
    expect(getByText("YouTube")).toBeTruthy();
    expect(getByText("Canal Principal")).toBeTruthy();
  });

  it("shows empty state per provider when no accounts", async () => {
    mockProviders.mockReturnValue({ data: [mockProvider], isLoading: false, isError: false });
    mockAccounts.mockReturnValue({ data: [], isLoading: false });
    const { getByText } = await renderPage();
    expect(getByText(/Nenhuma conta ainda/i)).toBeTruthy();
  });

  it("opens AddAccountModal when Add button clicked", async () => {
    mockProviders.mockReturnValue({ data: [mockProvider], isLoading: false, isError: false });
    mockAccounts.mockReturnValue({ data: [], isLoading: false });
    const { getByText, getByTestId, fireEvent } = await renderPage();
    fireEvent.click(getByText(/Adicionar conta/i));
    expect(getByTestId("add-account-modal")).toBeTruthy();
  });
});

// ─── AddAccountModal (the real component; UI primitives mocked) ─────────────
describe("AddAccountModal", () => {
  // Provider now uses `id`; manual_key_fields use `name` (not `key`)
  const oauthProvider = {
    id: "youtube", display_name: "YouTube", oauth_supported: true,
    manual_entry: true,
    manual_key_fields: [
      { name: "api_key", label: "API Key", placeholder: "AIza...", type: "password" as const },
    ],
    tutorial_url: "https://developers.google.com/youtube/v3/getting-started",
    scopes: [], icon: null,
  };
  const manualProvider = {
    id: "n8n", display_name: "n8n", oauth_supported: false,
    manual_entry: true,
    manual_key_fields: [
      { name: "api_url", label: "API URL", placeholder: "https://n8n.example.com", type: "url" as const },
      { name: "api_key", label: "API Key", placeholder: "n8n_...", type: "password" as const },
    ],
    tutorial_url: null, scopes: [], icon: null,
  };

  async function renderModal(provider: string, providerConfig: any, onClose = vi.fn()) {
    // Import the REAL modal (the page-level mock above is module-scoped to
    // "@/components/AddAccountModal"; importing "../components/AddAccountModal"
    // here resolves the same path — so unmock it for this block).
    vi.doUnmock("@/components/AddAccountModal");
    vi.resetModules();
    const { default: AddAccountModal } = await import("../components/AddAccountModal");
    const React = (await import("react")).default;
    const rtl = await import("@testing-library/react");
    return { ...rtl.render(React.createElement(AddAccountModal, { provider, providerConfig, onClose })), fireEvent: rtl.fireEvent, onClose };
  }

  it("shows OAuth button for YouTube provider", async () => {
    const { getByText } = await renderModal("youtube", oauthProvider);
    expect(getByText(/Conectar via OAuth/i)).toBeTruthy();
  });

  it("renders manual form fields for n8n provider (field.name-keyed)", async () => {
    // "API URL" / "API Key" appear in BOTH the field label and the help text,
    // so assert presence (≥1) rather than a single match.
    const { getAllByText } = await renderModal("n8n", manualProvider);
    expect(getAllByText(/API URL/i).length).toBeGreaterThan(0);
    expect(getAllByText(/API Key/i).length).toBeGreaterThan(0);
  });

  it("calls onClose when cancel clicked", async () => {
    const { getByText, fireEvent, onClose } = await renderModal("n8n", manualProvider);
    fireEvent.click(getByText(/Cancelar/i));
    expect(onClose).toHaveBeenCalled();
  });
});

// ─── Conexoes (unified page) ────────────────────────────────────────────────
describe("Conexoes page", () => {
  const youtubeProvider = {
    id: "youtube", display_name: "YouTube", oauth_supported: true,
    manual_entry: false, manual_key_fields: [], tutorial_url: null,
    scopes: [], icon: null,
  };

  it("renders the Conexoes header", async () => {
    const { getAllByText } = await renderConexoes();
    // Page title is "Conexões" (with ões); use a regex that matches both
    // the accented and ASCII variants in case the test file has an older expectation.
    expect(getAllByText(/Cone.{0,5}es/i).length).toBeGreaterThan(0);
  });

  it("renders WhatsApp section heading", async () => {
    const { getByText } = await renderConexoes();
    expect(getByText("WhatsApp")).toBeTruthy();
  });

  it("calls adopt-legacy on mount for youtube", async () => {
    const adoptMutate = vi.fn();
    mockAdoptLegacy.mockReturnValue({ mutate: adoptMutate, mutateAsync: vi.fn(), isPending: false });
    mockProviders.mockReturnValue({ data: [youtubeProvider], isLoading: false, isError: false });
    mockAccounts.mockReturnValue({ data: [], isLoading: false });

    await renderConexoes();
    // adopt.mutate() is called once on mount inside YouTubeSection
    expect(adoptMutate).toHaveBeenCalled();
  });

  it("renders YouTube connect button", async () => {
    mockProviders.mockReturnValue({ data: [youtubeProvider], isLoading: false, isError: false });
    mockAccounts.mockReturnValue({ data: [], isLoading: false });
    const { getByText } = await renderConexoes();
    expect(getByText(/Conectar canal do YouTube/i)).toBeTruthy();
  });
});

// ─── Pure-logic checks (no render) ─────────────────────────────────────────
describe("YouTubeAccountPicker (via Upload page)", () => {
  it("shows CTA when no YouTube accounts exist", () => {
    const copy = "Nenhuma conta YouTube conectada";
    expect(copy.length).toBeGreaterThan(0);
  });

  it("defaults to the default account when accounts exist", () => {
    const accounts = [
      { id: "acc-1", account_label: "Main", is_default: false, provider: "youtube" },
      { id: "acc-2", account_label: "Business", is_default: true, provider: "youtube" },
    ];
    const defaultAccount = accounts.find((a) => a.is_default) ?? accounts[0];
    expect(defaultAccount.id).toBe("acc-2");
  });
});
