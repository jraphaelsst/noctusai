/**
 * WhatsAppChat.tsx — unit tests for the WhatsApp dashboard page (Wave 5
 * SocialDashboardShell remodel).
 *
 * The old bespoke 2-pane chat markup is gone — this page now composes:
 *   - `SocialDashboardShell` (header + subtabs) — stubbed here (same
 *     prop-capture pattern as `WhatsAppChatWindow.test.tsx` / `IgDMs.test.tsx`)
 *     since the real `@noctusai/lib/design-system` barrel transitively
 *     imports `useAIOutputFor` → `@noctusai/seed/infra`, which throws at
 *     module-load time without `VITE_SUPABASE_URL`. The shell's OWN
 *     tab-switching mechanics are covered by
 *     `seed/lib/frontend/src/design-system/dashboard/SocialDashboardShell.test.tsx`.
 *   - `WhatsAppChatWindow` (Chat subtab) — stubbed; its WhatsApp→ChatWindow
 *     adapter mapping is covered by `components/WhatsAppChatWindow.test.tsx`.
 *   - `ConnectionSettingsPanel` (Configurações subtab) — stubbed; the WAHA
 *     management body itself has no dedicated test file (pre-existing gap,
 *     inherited from the pre-extraction `ConnectionDetailDialog`).
 *
 * Coverage:
 *   1. Loading state while connections load.
 *   2. Error state when connections fail to load.
 *   3. Empty state when no connections exist (no shell, link to /conexoes).
 *   4. Shell wiring: title/subtitle + subtab keys (chat, config).
 *   5. Connection selector (accountSwitcher slot) — renders one button per
 *      connection; clicking a button re-points the selected connection fed
 *      to BOTH subtabs.
 *   6. Deep-link default selection — `useActiveAccountStore.activeAccountId`
 *      pre-selects a matching connection over the first-in-list default.
 *   7. Chat subtab — renders `WhatsAppChatWindow` with the selected
 *      connection's id + auto_reply_enabled.
 *   8. Configurações subtab — renders `ConnectionSettingsPanel` with the
 *      selected connection's full `line` object.
 *   9. Configurações subtab delete — `onRequestDelete` opens the inline
 *      confirm dialog; confirming calls the remove mutation.
 *
 * Mock strategy: ONE vi.mock per module (hoisted); hooks are vi.fn()s
 * configured per-test in beforeEach.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

// ─── Hook mocks ────────────────────────────────────────────────────────────

const mockUseWhatsAppConnections = vi.fn();
const mockUseWhatsAppConnectionMutations = vi.fn();
vi.mock("@/hooks/useWhatsAppConnections", () => ({
  useWhatsAppConnections: mockUseWhatsAppConnections,
  useWhatsAppConnectionMutations: mockUseWhatsAppConnectionMutations,
}));

const mockActiveAccountState = { activeAccountId: null as string | null };
vi.mock("@/state/useActiveAccount", () => ({
  useActiveAccountStore: (selector: (s: typeof mockActiveAccountState) => unknown) =>
    selector(mockActiveAccountState),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// ─── UI stub ───────────────────────────────────────────────────────────────

vi.mock("@/components/ui/button", () => ({
  Button: ({ children, onClick, disabled, variant, ...rest }: any) => (
    <button onClick={onClick} disabled={disabled} data-variant={variant} {...rest}>
      {children}
    </button>
  ),
}));

// ─── Subtab-content stubs — capture props ─────────────────────────────────

let lastChatWindowProps: any = null;
vi.mock("@/components/WhatsAppChatWindow", () => ({
  WhatsAppChatWindow: (props: any) => {
    lastChatWindowProps = props;
    return <div data-testid="chat-window-stub">{`chat:${props.connectionId}`}</div>;
  },
}));

let lastConfigPanelProps: any = null;
vi.mock("@/components/ConnectionDetailDialog", () => ({
  ConnectionSettingsPanel: (props: any) => {
    lastConfigPanelProps = props;
    return <div data-testid="config-panel-stub">{`config:${props.line.id}`}</div>;
  },
}));

// ─── Shell stub — captures props for wiring assertions ────────────────────

let lastShellProps: any = null;
vi.mock("@noctusai/lib/design-system", () => ({
  SocialDashboardShell: (props: any) => {
    lastShellProps = props;
    return null;
  },
}));

// ─── Fixtures ──────────────────────────────────────────────────────────────

const makeConn = (overrides: Partial<Record<string, any>> = {}) => ({
  id: "conn-1",
  label: "Atendimento SP",
  base_url: "http://waha:3000",
  session_name: "sw_conn1",
  webhook_url: null,
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
  auto_reply_enabled: false,
  authorized_numbers: [],
  bound_chats: [],
  ...overrides,
});

beforeEach(() => {
  lastChatWindowProps = null;
  lastConfigPanelProps = null;
  lastShellProps = null;
  mockActiveAccountState.activeAccountId = null;

  mockUseWhatsAppConnections.mockReturnValue({
    data: [makeConn()],
    isLoading: false,
    isError: false,
  });
  mockUseWhatsAppConnectionMutations.mockReturnValue({
    remove: { mutate: vi.fn(), isPending: false },
  });
});

// ─── Render helper ─────────────────────────────────────────────────────────

async function renderPage() {
  const mod = await import("./WhatsAppChat");
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  const result = rtl.render(React.createElement(mod.default));
  return { ...result, rtl };
}

function getSubtab(key: string) {
  return lastShellProps.subtabs.find((s: any) => s.key === key);
}

// ─── Tests ─────────────────────────────────────────────────────────────────

describe("WhatsAppChat — connection states", () => {
  it("shows loading spinner while connections load", async () => {
    mockUseWhatsAppConnections.mockReturnValue({ data: [], isLoading: true, isError: false });
    const { getByText } = await renderPage();
    expect(getByText("Carregando conexões...")).toBeTruthy();
  });

  it("shows an error message when connections fail to load", async () => {
    mockUseWhatsAppConnections.mockReturnValue({ data: [], isLoading: false, isError: true });
    const { getByText } = await renderPage();
    expect(getByText("Erro ao carregar conexões. Recarregue a página.")).toBeTruthy();
  });

  it("shows empty state (no shell) when no connections exist, with a link to /conexoes", async () => {
    mockUseWhatsAppConnections.mockReturnValue({ data: [], isLoading: false, isError: false });
    const { getByText } = await renderPage();
    expect(getByText("Nenhuma conexão WhatsApp")).toBeTruthy();
    expect(getByText("Conexões")).toBeTruthy();
    expect(lastShellProps).toBeNull();
  });
});

describe("WhatsAppChat — shell wiring", () => {
  it("passes title/subtitle and Chat + Configurações subtabs to the shell", async () => {
    await renderPage();
    expect(lastShellProps.title).toBe("WhatsApp");
    expect(lastShellProps.defaultSubtab).toBe("chat");
    expect(lastShellProps.subtabs.map((s: any) => s.key)).toEqual(["chat", "config"]);
    expect(lastShellProps.subtabs.map((s: any) => s.label)).toEqual(["Chat", "Configurações"]);
  });
});

describe("WhatsAppChat — connection selector", () => {
  it("renders one button per connection in the accountSwitcher slot", async () => {
    mockUseWhatsAppConnections.mockReturnValue({
      data: [makeConn({ id: "c1", label: "SP" }), makeConn({ id: "c2", label: "RJ" })],
      isLoading: false,
      isError: false,
    });
    const { rtl } = await renderPage();
    const { getByText } = rtl.render(lastShellProps.accountSwitcher);
    expect(getByText("SP")).toBeTruthy();
    expect(getByText("RJ")).toBeTruthy();
  });

  it("switching connections re-points both subtabs", async () => {
    mockUseWhatsAppConnections.mockReturnValue({
      data: [makeConn({ id: "c1", label: "SP" }), makeConn({ id: "c2", label: "RJ" })],
      isLoading: false,
      isError: false,
    });
    const { rtl } = await renderPage();

    // Default selection is the first connection.
    expect(getSubtab("chat").render().props.connection.id).toBe("c1");

    // The accountSwitcher's onChange is the page's real setSelectedConnId —
    // calling it re-renders the mounted WhatsAppChat instance (the shell
    // mock returns null but the page component itself stays mounted).
    rtl.act(() => {
      lastShellProps.accountSwitcher.props.onChange("c2");
    });

    expect(getSubtab("chat").render().props.connection.id).toBe("c2");
    expect(getSubtab("config").render().props.connection.id).toBe("c2");
  });
});

describe("WhatsAppChat — deep-link default selection", () => {
  it("prefers the active-account-store connection over the first-in-list default", async () => {
    mockActiveAccountState.activeAccountId = "c2";
    mockUseWhatsAppConnections.mockReturnValue({
      data: [makeConn({ id: "c1", label: "SP" }), makeConn({ id: "c2", label: "RJ" })],
      isLoading: false,
      isError: false,
    });
    await renderPage();
    expect(getSubtab("chat").render().props.connection.id).toBe("c2");
  });

  it("falls back to the first connection when the active account isn't a WA connection", async () => {
    mockActiveAccountState.activeAccountId = "some-other-provider-account";
    mockUseWhatsAppConnections.mockReturnValue({
      data: [makeConn({ id: "c1", label: "SP" })],
      isLoading: false,
      isError: false,
    });
    await renderPage();
    expect(getSubtab("chat").render().props.connection.id).toBe("c1");
  });
});

describe("WhatsAppChat — Chat subtab", () => {
  it("renders WhatsAppChatWindow with the selected connection's id and auto_reply_enabled", async () => {
    mockUseWhatsAppConnections.mockReturnValue({
      data: [makeConn({ id: "conn-9", auto_reply_enabled: true })],
      isLoading: false,
      isError: false,
    });
    const { rtl } = await renderPage();
    rtl.render(getSubtab("chat").render());
    expect(lastChatWindowProps.connectionId).toBe("conn-9");
    expect(lastChatWindowProps.autoReplyEnabled).toBe(true);
  });
});

describe("WhatsAppChat — Configurações subtab", () => {
  it("renders ConnectionSettingsPanel with the selected connection's full line", async () => {
    const conn = makeConn({ id: "conn-9", label: "Atendimento RJ" });
    mockUseWhatsAppConnections.mockReturnValue({ data: [conn], isLoading: false, isError: false });
    const { rtl } = await renderPage();
    rtl.render(getSubtab("config").render());
    expect(lastConfigPanelProps.line).toEqual(conn);
  });

  it("onRequestDelete opens the inline confirm dialog; confirming calls the remove mutation", async () => {
    const conn = makeConn({ id: "conn-9", label: "Atendimento RJ" });
    mockUseWhatsAppConnections.mockReturnValue({ data: [conn], isLoading: false, isError: false });
    const mutate = vi.fn();
    mockUseWhatsAppConnectionMutations.mockReturnValue({ remove: { mutate, isPending: false } });

    const { rtl, getByText, getByTestId } = await renderPage();
    rtl.render(getSubtab("config").render());

    rtl.act(() => {
      lastConfigPanelProps.onRequestDelete(conn);
    });

    expect(getByText('"Atendimento RJ" será removida permanentemente.')).toBeTruthy();
    rtl.fireEvent.click(getByTestId("wa-confirm-delete"));
    expect(mutate).toHaveBeenCalledWith("conn-9", expect.any(Object));
  });
});
