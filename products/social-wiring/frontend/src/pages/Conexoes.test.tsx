/**
 * Conexoes page integration tests — P2 card refactor.
 *
 * Tests:
 *   1. Conexoes renders IntegrationCard for each YouTube account
 *   2. Conexoes groups accounts by client (client section header + unassigned)
 *   3. Conexoes shows empty state when no YouTube accounts
 *   4. AccountSwitcher renders client + account dropdowns and reflects
 *      the active selection via the store
 *
 * Mock strategy:
 *   · ONE vi.mock per module (hoisted). Multiple mocks of the same module
 *     collide; the last wins silently.
 *   · All hooks are vi.fn()s configured per-test in beforeEach.
 *   · UI primitives mocked as JSX (single React instance).
 *   · @noctusai/lib's IntegrationCard and IntegrationCardModal are mocked
 *     as lightweight rendering stubs so the test does not need the full
 *     lib render pipeline (avoids dual-React null-useState gap).
 *   · localStorage/sessionStorage are provisioned by the shared seed vitest
 *     setup (seed/framework/frontend/vitest.setup.ts) — no per-file polyfill.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
  // Reset the zustand active-account store between tests
  const { useActiveAccountStore } = await import("@/state/useActiveAccount");
  useActiveAccountStore.setState({ activeAccountIdByProvider: {}, activeMarcaId: null });
});

// ─── Hook mocks ────────────────────────────────────────────────────────────

const mockIntegrationAccounts = vi.fn();
const mockUpdateAccount = vi.fn();
const mockSetDefaultAccount = vi.fn();
const mockDeleteAccount = vi.fn();
const mockSyncAccount = vi.fn();
const mockAdoptLegacy = vi.fn();
const mockOAuthStart = vi.fn();

// `useStartProviderOAuth` / `useSubmitInstagramToken` are consumed by the
// Instagram section Conexoes now mounts. Omitting them here made all 11 tests
// fail with "is not a function" — the module mock must cover every export the
// page's tree reaches, not just the ones the assertions touch.
const mockProviderOAuthStart = vi.fn();
const mockSubmitInstagramToken = vi.fn();

vi.mock("@/hooks/useIntegrationAccounts", () => ({
  useIntegrationAccounts: mockIntegrationAccounts,
  useUpdateAccount: mockUpdateAccount,
  useSetDefaultAccount: mockSetDefaultAccount,
  useDeleteAccount: mockDeleteAccount,
  useSyncAccount: mockSyncAccount,
  useAdoptLegacy: mockAdoptLegacy,
  useStartYouTubeOAuth: mockOAuthStart,
  useStartProviderOAuth: mockProviderOAuthStart,
  useSubmitInstagramToken: mockSubmitInstagramToken,
}));

const mockClients = vi.fn();
const mockCreateClient = vi.fn();
const mockUpdateClient = vi.fn();
const mockDeleteClient = vi.fn();

vi.mock("@/hooks/useMarcas", () => ({
  useMarcas: mockClients,
  useCreateMarca: mockCreateClient,
  useUpdateMarca: mockUpdateClient,
  useDeleteMarca: mockDeleteClient,
}));

// WhatsApp (Conexao / ConnectionDetailDialog are now imported by Conexoes)
vi.mock("@/hooks/useWhatsAppConnections", () => ({
  useWhatsAppConnections: vi.fn(() => ({ data: [], isLoading: false })),
  useWhatsAppConnectionMutations: vi.fn(() => ({
    create: { mutate: vi.fn(), isPending: false },
    update: { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false },
    remove: { mutate: vi.fn(), isPending: false },
  })),
  useWhatsAppConnectionStatus: vi.fn(() => ({ data: null })),
  useWhatsAppConnectionQr: vi.fn(() => ({ data: null })),
  useRecoverConnection: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useWhatsAppConnectionActions: vi.fn(() => ({
    start: { mutate: vi.fn(), isPending: false },
    restart: { mutate: vi.fn(), isPending: false },
    logout: { mutate: vi.fn(), isPending: false },
    configureWebhook: { mutate: vi.fn(), isPending: false },
  })),
  useRevealApiKey: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useConnectionChats: vi.fn(() => ({ data: [], isLoading: false, isError: false })),
  useToggleAutoReply: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));

// react-router-dom
vi.mock("react-router-dom", () => ({
  useSearchParams: vi.fn(() => [new URLSearchParams(), vi.fn()]),
  Link: ({ children, to, ...rest }: any) => <a href={to} {...rest}>{children}</a>,
}));

// @noctusai/lib — stub IntegrationCard + IntegrationCardModal
vi.mock("@noctusai/lib", () => ({
  IntegrationCard: ({ account }: any) => (
    <div
      data-testid="integration-card"
      data-account-id={account?.id}
      data-account-label={account?.account_label}
    >
      {account?.account_label}
    </div>
  ),
  IntegrationCardModal: ({ account, onClose }: any) =>
    account ? (
      <div data-testid="integration-card-modal">
        <button onClick={onClose}>Fechar modal</button>
      </div>
    ) : null,
  resolveStatusBadge: (status: string) => ({
    label: status,
    className: "test-badge",
    showSpinner: false,
  }),
}));

// UI primitive mocks
vi.mock("@/components/ui/separator", () => ({ Separator: () => null }));
vi.mock("@/components/ui/button", () => ({
  Button: ({ children, onClick, disabled }: any) => (
    <button onClick={onClick} disabled={disabled}>{children}</button>
  ),
}));
vi.mock("@/components/MarcaManagementModal", () => ({
  MarcaManagementModal: ({ onClose }: any) => (
    <div data-testid="client-management-modal">
      <button onClick={onClose}>Fechar</button>
    </div>
  ),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

// ─── Fixtures ──────────────────────────────────────────────────────────────

const clientA = {
  id: "client-a", org_id: "org-1", slug: "acme", name: "Acme Corp",
  kind: "partner", notes: null, created_at: "2026-01-01", updated_at: "2026-01-01",
};
const clientB = {
  id: "client-b", org_id: "org-1", slug: "beta", name: "Beta Ltd",
  kind: null, notes: null, created_at: "2026-01-01", updated_at: "2026-01-01",
};

const makeAccount = (overrides: Partial<{
  id: string; account_label: string; marca_id: string | null; status: string;
  is_default: boolean; channel_info: Record<string, unknown>;
}> = {}) => ({
  id: overrides.id ?? "acc-1",
  org_id: "org-1",
  provider: "youtube",
  account_label: overrides.account_label ?? "Canal Principal",
  marca_id: overrides.marca_id ?? null,
  status: overrides.status ?? "validated",
  channel_info: overrides.channel_info ?? { title: "My Channel", subscriber_count: 1000 },
  metadata: {},
  is_default: overrides.is_default ?? false,
  last_synced_at: null,
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
});

// ─── Defaults per test ─────────────────────────────────────────────────────

beforeEach(() => {
  // isPending/isFetching alongside isLoading: the YouTube section reads
  // isLoading, the Instagram section reads `isPending || isFetching` (the
  // non-lying gate). A mock missing the latter silently renders the Instagram
  // empty state during what should be a loading frame.
  setAccounts({
    data: [],
    isLoading: false,
    isPending: false,
    isFetching: false,
    isError: false,
  });
  mockClients.mockReturnValue({ data: [], isLoading: false, isError: false });
  mockUpdateAccount.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockSetDefaultAccount.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockDeleteAccount.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockSyncAccount.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockAdoptLegacy.mockReturnValue({ mutate: vi.fn(), isPending: false });
  mockOAuthStart.mockReturnValue({ mutate: vi.fn(), isPending: false });
  mockProviderOAuthStart.mockReturnValue({ mutate: vi.fn(), isPending: false });
  mockSubmitInstagramToken.mockReturnValue({ mutate: vi.fn(), isPending: false });
  mockCreateClient.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockUpdateClient.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockDeleteClient.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
});


// ─── Provider-aware account mock ───────────────────────────────────────────
// `useIntegrationAccounts(provider)` returns a DIFFERENT set per provider in
// reality. The flat mockReturnValue used before this section existed handed the
// YouTube dataset to every caller, so the Instagram section rendered YouTube's
// cards and the global `integration-card` counts doubled. `setAccounts` keeps
// the per-test dataset scoped to YouTube and answers other providers empty.
function setAccounts(result: Record<string, unknown>) {
  mockIntegrationAccounts.mockImplementation((provider?: string) =>
    provider === undefined || provider === "youtube"
      ? result
      : { data: [], isLoading: false, isPending: false, isFetching: false, isError: false },
  );
}

// ─── Helpers ──────────────────────────────────────────────────────────────

async function renderConexoes() {
  const { default: Conexoes } = await import("./Conexoes");
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  return { ...rtl.render(React.createElement(Conexoes)), fireEvent: rtl.fireEvent };
}

async function renderAccountSwitcher(
  accounts: any[] = [],
  marcas: any[] = [],
) {
  const { AccountSwitcher } = await import("@/components/AccountSwitcher");
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  return {
    ...rtl.render(
      React.createElement(AccountSwitcher, { accounts, marcas }),
    ),
    fireEvent: rtl.fireEvent,
  };
}

// ─── Conexoes tests ────────────────────────────────────────────────────────

describe("Conexoes — IntegrationCard rendering", () => {
  it("renders an IntegrationCard for each YouTube account", async () => {
    const accounts = [
      makeAccount({ id: "acc-1", account_label: "Canal 1" }),
      makeAccount({ id: "acc-2", account_label: "Canal 2" }),
    ];
    setAccounts({
      data: accounts, isLoading: false, isError: false,
    });

    const { getAllByTestId } = await renderConexoes();
    const cards = getAllByTestId("integration-card");
    expect(cards.length).toBe(2);
  });

  it("renders the page header", async () => {
    const { getAllByText } = await renderConexoes();
    expect(getAllByText(/Conexões/i).length).toBeGreaterThan(0);
  });

  it("renders WhatsApp section", async () => {
    const { getByText } = await renderConexoes();
    expect(getByText("WhatsApp")).toBeTruthy();
  });
});

describe("Conexoes — empty state", () => {
  it("shows empty state when no YouTube accounts", async () => {
    setAccounts({
      data: [], isLoading: false, isError: false,
    });
    const { getByText } = await renderConexoes();
    expect(getByText(/Nenhuma conta YouTube conectada/i)).toBeTruthy();
  });

  it("shows loading spinner while accounts loading", async () => {
    setAccounts({
      data: [], isLoading: true, isError: false,
    });
    const { getByText } = await renderConexoes();
    expect(getByText(/Carregando contas YouTube/i)).toBeTruthy();
  });

  it("shows error state when accounts fail to load", async () => {
    setAccounts({
      data: [], isLoading: false, isError: true,
    });
    const { getByText } = await renderConexoes();
    expect(getByText(/Erro ao carregar contas/i)).toBeTruthy();
  });
});

describe("Conexoes — client grouping", () => {
  it("renders a section header for each client that has accounts", async () => {
    const accounts = [
      makeAccount({ id: "acc-1", marca_id: "client-a", account_label: "Canal Acme" }),
      makeAccount({ id: "acc-2", marca_id: null, account_label: "Canal Livre" }),
    ];
    setAccounts({
      data: accounts, isLoading: false, isError: false,
    });
    mockClients.mockReturnValue({
      data: [clientA], isLoading: false, isError: false,
    });

    const { getAllByText } = await renderConexoes();
    // "Acme Corp" appears in both the OAuth client dropdown option and the section header
    expect(getAllByText("Acme Corp").length).toBeGreaterThanOrEqual(1);
    // Unassigned group: "Sem cliente" appears in both the OAuth dropdown option
    // and the section header
    expect(getAllByText("Sem cliente").length).toBeGreaterThanOrEqual(1);
  });

  it("renders both accounts in the correct groups", async () => {
    const accounts = [
      makeAccount({ id: "acc-1", marca_id: "client-a", account_label: "Canal Acme" }),
      makeAccount({ id: "acc-2", marca_id: null, account_label: "Canal Livre" }),
    ];
    setAccounts({
      data: accounts, isLoading: false, isError: false,
    });
    mockClients.mockReturnValue({
      data: [clientA], isLoading: false, isError: false,
    });

    const { getAllByTestId } = await renderConexoes();
    const cards = getAllByTestId("integration-card");
    expect(cards.length).toBe(2);
    expect(cards[0].getAttribute("data-account-label")).toBe("Canal Acme");
    expect(cards[1].getAttribute("data-account-label")).toBe("Canal Livre");
  });

  it("shows Gerenciar marcas button", async () => {
    const { getByText } = await renderConexoes();
    expect(getByText(/Gerenciar marcas/i)).toBeTruthy();
  });

  it("opens MarcaManagementModal when Gerenciar marcas clicked", async () => {
    const { getByText, getByTestId, fireEvent } = await renderConexoes();
    fireEvent.click(getByText(/Gerenciar marcas/i));
    expect(getByTestId("client-management-modal")).toBeTruthy();
  });
});

describe("Conexoes — adopt-legacy on mount", () => {
  it("calls adopt-legacy mutate on mount", async () => {
    const adoptMutate = vi.fn();
    mockAdoptLegacy.mockReturnValue({
      mutate: adoptMutate, isPending: false,
    });
    await renderConexoes();
    expect(adoptMutate).toHaveBeenCalled();
  });
});

// ─── AccountSwitcher tests ─────────────────────────────────────────────────

describe("AccountSwitcher", () => {
  const accounts = [
    makeAccount({ id: "acc-1", account_label: "Canal 1", marca_id: "client-a", is_default: true }),
    makeAccount({ id: "acc-2", account_label: "Canal 2", marca_id: null }),
  ];

  it("renders account dropdown with account options", async () => {
    const { getAllByRole } = await renderAccountSwitcher(accounts, []);
    // Should have a select for accounts
    const selects = getAllByRole("combobox");
    expect(selects.length).toBeGreaterThan(0);
  });

  it("renders client dropdown when clients are provided", async () => {
    const { getAllByRole } = await renderAccountSwitcher(accounts, [clientA, clientB]);
    const selects = getAllByRole("combobox");
    // At least 2 dropdowns: client + account
    expect(selects.length).toBeGreaterThanOrEqual(2);
  });

  it("account dropdown reflects this provider's selection from store", async () => {
    // Pre-set store (the harness renders <AccountSwitcher> with no provider
    // prop, so it reads and writes the default "youtube" slot).
    const { useActiveAccountStore } = await import("@/state/useActiveAccount");
    useActiveAccountStore.setState({
      activeAccountIdByProvider: { youtube: "acc-1" },
      activeMarcaId: null,
    });

    const { getAllByRole } = await renderAccountSwitcher(accounts, [clientA]);
    const selects = getAllByRole("combobox");
    // The account select should show acc-1 as selected
    const accountSelect = selects[selects.length - 1] as HTMLSelectElement;
    expect(accountSelect.value).toBe("acc-1");
  });

  it("ignores a selection belonging to a different provider", async () => {
    // A Meta selection must not render as this YouTube switcher's value —
    // the display half of the cross-provider leak behind the live n8n 404
    // on 2026-07-31.
    const { useActiveAccountStore } = await import("@/state/useActiveAccount");
    useActiveAccountStore.setState({
      activeAccountIdByProvider: { meta: "acc-1" },
      activeMarcaId: null,
    });

    const { getAllByRole } = await renderAccountSwitcher(accounts, [clientA]);
    const selects = getAllByRole("combobox");
    const accountSelect = selects[selects.length - 1] as HTMLSelectElement;
    expect(accountSelect.value).toBe("");
  });

  it("switching account updates only this provider's slot", async () => {
    const { useActiveAccountStore } = await import("@/state/useActiveAccount");
    useActiveAccountStore.setState({
      activeAccountIdByProvider: { n8n: "n8n-account" },
      activeMarcaId: null,
    });

    const { getAllByRole, fireEvent } = await renderAccountSwitcher(accounts, []);
    const selects = getAllByRole("combobox");
    const accountSelect = selects[selects.length - 1];
    fireEvent.change(accountSelect, { target: { value: "acc-2" } });

    const state = useActiveAccountStore.getState();
    expect(state.activeAccountIdByProvider["youtube"]).toBe("acc-2");
    // Picking a YouTube account leaves the n8n page pointed where it was.
    expect(state.activeAccountIdByProvider["n8n"]).toBe("n8n-account");
  });
});
