/**
 * WhatsAppWorkspace.tsx + the two Lais route pages (`Conversas.tsx`,
 * `Configuracoes.tsx`) — unit tests. Successor of the former
 * `pages/WhatsAppChat.test.tsx` (single /whatsapp-chat page with Chat +
 * Configurações subtabs), split into two routes on 2026-10-13.
 *
 * Composition under test:
 *   - `SocialDashboardShell` — stubbed (prop capture, same pattern as
 *     `WhatsAppChatWindow.test.tsx` / `IgDMs.test.tsx`): the real
 *     `@noctusai/lib/design-system` barrel transitively imports
 *     `useAIOutputFor` → `@noctusai/seed/infra`, which throws at module load
 *     without `VITE_SUPABASE_URL`. The shell's own tab mechanics are covered by
 *     `seed/lib/frontend/src/design-system/dashboard/SocialDashboardShell.test.tsx`.
 *   - `WhatsAppChatWindow` (Conversas) — stubbed; covered by
 *     `components/WhatsAppChatWindow.test.tsx`.
 *   - `ConnectionSettingsPanel` (Configurações) — stubbed.
 *   - `useActiveAccountStore` — the REAL zustand store: the shared selection
 *     across both routes IS the behaviour under test, so it is not faked.
 *
 * Coverage:
 *   1. Loading / error / empty states.
 *   2. Shell wiring per route: Lais-labelled title, one "WhatsApp" subtab.
 *   3. Each route renders its view (Conversas → chat window, Configurações →
 *      settings panel) — both route modules default-export a working page.
 *   4. Connection selector — one button per connection; picking one writes the
 *      shared store and re-points the view.
 *   5. Shared selection — a connection picked on Conversas is the one
 *      Configurações opens with (cross-route sharing via the store).
 *   6. Deep-link pre-selection — a `whatsapp` store entry (written by the
 *      IntegrationCard click) wins over first-in-list; a foreign id falls back.
 *   7. Configurações delete — onRequestDelete opens the confirm; confirming
 *      calls the remove mutation.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

import { useActiveAccountStore } from "@/state/useActiveAccount";

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

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// ─── UI stub ───────────────────────────────────────────────────────────────

vi.mock("@/components/ui/button", () => ({
  Button: ({ children, onClick, disabled, variant, ...rest }: any) => (
    <button onClick={onClick} disabled={disabled} data-variant={variant} {...rest}>
      {children}
    </button>
  ),
}));

// ─── View-content stubs — capture props ───────────────────────────────────

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

const twoConns = () => ({
  data: [makeConn({ id: "c1", label: "SP" }), makeConn({ id: "c2", label: "RJ" })],
  isPending: false,
  isError: false,
});

beforeEach(() => {
  lastChatWindowProps = null;
  lastConfigPanelProps = null;
  lastShellProps = null;
  useActiveAccountStore.setState({ activeAccountIdByProvider: {}, activeMarcaId: null });

  mockUseWhatsAppConnections.mockReturnValue({
    data: [makeConn()],
    isPending: false,
    isError: false,
  });
  mockUseWhatsAppConnectionMutations.mockReturnValue({
    remove: { mutate: vi.fn(), isPending: false },
  });
});

// ─── Render helpers ────────────────────────────────────────────────────────

type Route = "conversas" | "configuracoes";

async function renderRoute(route: Route) {
  const mod =
    route === "conversas" ? await import("./Conversas") : await import("./Configuracoes");
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  const result = rtl.render(React.createElement(mod.default));
  return { ...result, rtl };
}

/** Render the shell's single subtab body (the route's view). */
async function renderView() {
  const rtl = await import("@testing-library/react");
  expect(lastShellProps.subtabs).toHaveLength(1);
  return rtl.render(lastShellProps.subtabs[0].render());
}

// ─── Tests ─────────────────────────────────────────────────────────────────

describe("Lais WhatsApp — connection states", () => {
  it("shows the loading state while connections load", async () => {
    mockUseWhatsAppConnections.mockReturnValue({ data: undefined, isPending: true, isError: false });
    const { getByText } = await renderRoute("conversas");
    expect(getByText("Carregando conexões...")).toBeTruthy();
    expect(lastShellProps).toBeNull();
  });

  it("shows the error state when connections fail to load", async () => {
    mockUseWhatsAppConnections.mockReturnValue({ data: undefined, isPending: false, isError: true });
    const { getByText } = await renderRoute("configuracoes");
    expect(getByText("Erro ao carregar conexões. Recarregue a página.")).toBeTruthy();
    expect(lastShellProps).toBeNull();
  });

  it("shows the empty state (link to Conexões) when there are no connections", async () => {
    mockUseWhatsAppConnections.mockReturnValue({ data: [], isPending: false, isError: false });
    const { getByText } = await renderRoute("conversas");
    expect(getByText("Nenhuma conexão WhatsApp")).toBeTruthy();
    expect(getByText("Conexões")).toBeTruthy();
    expect(lastShellProps).toBeNull();
  });
});

describe("Lais WhatsApp — /lais/conversas", () => {
  it("renders the shell titled from the Lais label with one WhatsApp subtab", async () => {
    const { LAIS_LABEL } = await import("@/nav/lais");
    await renderRoute("conversas");
    expect(lastShellProps.title).toBe(`${LAIS_LABEL} · Conversas`);
    expect(lastShellProps.subtabs.map((s: any) => s.key)).toEqual(["whatsapp"]);
    expect(lastShellProps.defaultSubtab).toBe("whatsapp");
  });

  it("renders WhatsAppChatWindow with the selected connection's id + auto_reply_enabled", async () => {
    mockUseWhatsAppConnections.mockReturnValue({
      data: [makeConn({ id: "conn-9", auto_reply_enabled: true })],
      isPending: false,
      isError: false,
    });
    await renderRoute("conversas");
    const { getByTestId } = await renderView();
    expect(getByTestId("chat-window-stub")).toBeTruthy();
    expect(lastChatWindowProps.connectionId).toBe("conn-9");
    expect(lastChatWindowProps.autoReplyEnabled).toBe(true);
    expect(lastConfigPanelProps).toBeNull();
  });
});

describe("Lais WhatsApp — /lais/configuracoes", () => {
  it("renders the shell titled from the Lais label", async () => {
    const { LAIS_LABEL } = await import("@/nav/lais");
    await renderRoute("configuracoes");
    expect(lastShellProps.title).toBe(`${LAIS_LABEL} · Configurações`);
  });

  it("renders ConnectionSettingsPanel with the selected connection's full line", async () => {
    const conn = makeConn({ id: "conn-9", label: "Atendimento RJ" });
    mockUseWhatsAppConnections.mockReturnValue({ data: [conn], isPending: false, isError: false });
    await renderRoute("configuracoes");
    const { getByTestId } = await renderView();
    expect(getByTestId("config-panel-stub")).toBeTruthy();
    expect(lastConfigPanelProps.line).toEqual(conn);
    expect(lastChatWindowProps).toBeNull();
  });

  it("onRequestDelete opens the inline confirm dialog; confirming calls the remove mutation", async () => {
    const conn = makeConn({ id: "conn-9", label: "Atendimento RJ" });
    mockUseWhatsAppConnections.mockReturnValue({ data: [conn], isPending: false, isError: false });
    const mutate = vi.fn();
    mockUseWhatsAppConnectionMutations.mockReturnValue({ remove: { mutate, isPending: false } });

    const { rtl, getByText, getByTestId } = await renderRoute("configuracoes");
    await renderView();

    rtl.act(() => {
      lastConfigPanelProps.onRequestDelete(conn);
    });

    expect(getByText('"Atendimento RJ" será removida permanentemente.')).toBeTruthy();
    rtl.fireEvent.click(getByTestId("wa-confirm-delete"));
    expect(mutate).toHaveBeenCalledWith("conn-9", expect.any(Object));
  });
});

describe("Lais WhatsApp — connection selector (shared across routes)", () => {
  it("renders one button per connection in the accountSwitcher slot", async () => {
    mockUseWhatsAppConnections.mockReturnValue(twoConns());
    const { rtl } = await renderRoute("conversas");
    const { getByText } = rtl.render(lastShellProps.accountSwitcher);
    expect(getByText("SP")).toBeTruthy();
    expect(getByText("RJ")).toBeTruthy();
  });

  it("picking a connection writes the shared store and re-points the view", async () => {
    mockUseWhatsAppConnections.mockReturnValue(twoConns());
    const { rtl } = await renderRoute("conversas");

    expect(lastShellProps.subtabs[0].render().props.connection.id).toBe("c1");

    rtl.act(() => {
      lastShellProps.accountSwitcher.props.onChange("c2");
    });

    expect(useActiveAccountStore.getState().activeAccountIdByProvider.whatsapp).toBe("c2");
    expect(lastShellProps.subtabs[0].render().props.connection.id).toBe("c2");
  });

  it("a connection picked on Conversas is the one Configurações opens with", async () => {
    mockUseWhatsAppConnections.mockReturnValue(twoConns());
    const first = await renderRoute("conversas");
    first.rtl.act(() => {
      lastShellProps.accountSwitcher.props.onChange("c2");
    });
    first.unmount();

    await renderRoute("configuracoes");
    expect(lastShellProps.accountSwitcher.props.selectedId).toBe("c2");
    expect(lastShellProps.subtabs[0].render().props.connection.id).toBe("c2");
  });
});

describe("Lais WhatsApp — deep-link pre-selection", () => {
  it("prefers the store's whatsapp connection over the first-in-list default", async () => {
    useActiveAccountStore.getState().setActiveAccount("whatsapp", "c2");
    mockUseWhatsAppConnections.mockReturnValue(twoConns());
    await renderRoute("conversas");
    expect(lastShellProps.subtabs[0].render().props.connection.id).toBe("c2");
  });

  it("falls back to the first connection when the stored id isn't a WA connection", async () => {
    useActiveAccountStore.getState().setActiveAccount("whatsapp", "some-stale-id");
    mockUseWhatsAppConnections.mockReturnValue(twoConns());
    await renderRoute("configuracoes");
    expect(lastShellProps.subtabs[0].render().props.connection.id).toBe("c1");
  });
});
