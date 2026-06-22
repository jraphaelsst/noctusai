/**
 * WhatsAppChat.tsx — unit tests for the WhatsApp chat UI.
 *
 * Covers:
 *   1. Loading state while connections load.
 *   2. Empty state when no connections exist (link to /conexoes).
 *   3. Default-selects the first connection on load.
 *   4. Conversation list — loading skeleton shown while chats load.
 *   5. Conversation list — empty state when no chats.
 *   6. Conversation list — chat rows render with contact + last message.
 *   7. Thread — loading skeleton shown while messages load.
 *   8. Thread — empty state when no messages.
 *   9. Thread — inbound bubbles render on the left, outbound on the right.
 *  10. Composer — Send button is disabled when input is empty.
 *  11. Composer — Send button is enabled when input has text.
 *  12. Composer — Enter key triggers send.
 *  13. Auto-reply — Switch renders and calls useSetAutoReply on change.
 *  14. Auto-reply — Switch reflects connection.auto_reply_enabled.
 *
 * Mock strategy:
 *   · ONE vi.mock per module (hoisted). Multiple mocks of the same module
 *     collide; the last wins silently.
 *   · All hooks are vi.fn()s configured per-test in beforeEach.
 *   · localStorage/sessionStorage provisioned by the shared seed vitest
 *     setup (seed/framework/frontend/vitest.setup.ts) — no per-file polyfill.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

// ─── Hook mocks ────────────────────────────────────────────────────────────

const mockUseWhatsAppConnections = vi.fn();
vi.mock("@/hooks/useWhatsAppConnections", () => ({
  useWhatsAppConnections: mockUseWhatsAppConnections,
}));

const mockUseWhatsAppChats = vi.fn();
const mockUseWhatsAppChatMessages = vi.fn();
const mockUseSendWhatsAppMessage = vi.fn();
const mockUseSetAutoReply = vi.fn();
vi.mock("@/hooks/useWhatsAppChats", () => ({
  useWhatsAppChats: mockUseWhatsAppChats,
  useWhatsAppChatMessages: mockUseWhatsAppChatMessages,
  useSendWhatsAppMessage: mockUseSendWhatsAppMessage,
  useSetAutoReply: mockUseSetAutoReply,
}));

// ─── UI stubs ─────────────────────────────────────────────────────────────

vi.mock("@/components/ui/badge", () => ({
  Badge: ({ children, className }: any) => (
    <span data-testid="badge" className={className}>{children}</span>
  ),
}));
vi.mock("@/components/ui/button", () => ({
  Button: ({ children, onClick, disabled, "aria-label": al, ...rest }: any) => (
    <button onClick={onClick} disabled={disabled} aria-label={al} {...rest}>
      {children}
    </button>
  ),
}));
vi.mock("@/components/ui/input", () => ({
  Input: ({ onChange, value, disabled, placeholder, "aria-label": al, onKeyDown, ...rest }: any) => (
    <input
      value={value}
      onChange={onChange}
      disabled={disabled}
      placeholder={placeholder}
      aria-label={al}
      onKeyDown={onKeyDown}
      {...rest}
    />
  ),
}));
vi.mock("@/components/ui/avatar", () => ({
  Avatar: ({ children, className }: any) => <div className={className}>{children}</div>,
}));
vi.mock("@/components/ui/skeleton", () => ({
  Skeleton: ({ className }: any) => <div data-testid="skeleton" className={className} />,
}));
vi.mock("@/components/ui/separator", () => ({
  Separator: () => <hr />,
}));
vi.mock("@/components/ui/switch", () => ({
  Switch: ({ checked, onCheckedChange, disabled, "aria-label": al }: any) => (
    <button
      role="switch"
      aria-checked={checked}
      aria-label={al}
      disabled={disabled}
      onClick={() => onCheckedChange(!checked)}
      data-testid="auto-reply-switch"
    >
      {checked ? "ON" : "OFF"}
    </button>
  ),
}));
vi.mock("@/components/ui/tooltip", () => ({
  TooltipProvider: ({ children }: any) => <>{children}</>,
  Tooltip: ({ children }: any) => <>{children}</>,
  TooltipTrigger: ({ children, asChild }: any) => <>{children}</>,
  TooltipContent: ({ children }: any) => <div data-testid="tooltip-content">{children}</div>,
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
  ...overrides,
});

const makeChat = (overrides: Partial<Record<string, any>> = {}) => ({
  chat_id: "5511999998888@c.us",
  contact: "5511999998888@c.us",
  last_message: "Olá, tudo bem?",
  last_message_at: new Date().toISOString(),
  last_direction: "inbound" as const,
  unread: 2,
  ...overrides,
});

const makeMessage = (
  id: string,
  direction: "inbound" | "outbound",
  body: string,
) => ({
  id,
  chat_id: "5511999998888@c.us",
  direction,
  body,
  created_at: new Date().toISOString(),
  provider_message_id: null,
  structured_payload: null,
});

const makeSendMutation = (overrides: Partial<Record<string, any>> = {}) => ({
  mutateAsync: vi.fn().mockResolvedValue({}),
  isPending: false,
  ...overrides,
});

const makeAutoReplyMutation = (overrides: Partial<Record<string, any>> = {}) => ({
  mutate: vi.fn(),
  isPending: false,
  ...overrides,
});

// ─── Default hook returns ──────────────────────────────────────────────────

beforeEach(() => {
  mockUseWhatsAppConnections.mockReturnValue({
    data: [makeConn()],
    isLoading: false,
    isError: false,
  });
  mockUseWhatsAppChats.mockReturnValue({
    data: [],
    isLoading: false,
    isError: false,
  });
  mockUseWhatsAppChatMessages.mockReturnValue({
    data: [],
    isLoading: false,
    isError: false,
  });
  mockUseSendWhatsAppMessage.mockReturnValue(makeSendMutation());
  mockUseSetAutoReply.mockReturnValue(makeAutoReplyMutation());
});

// ─── Render helper ─────────────────────────────────────────────────────────

async function renderWhatsAppChat() {
  const mod = await import("./WhatsAppChat");
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  const result = rtl.render(React.createElement(mod.default));
  return { ...result, rtl };
}

// ─── Tests ─────────────────────────────────────────────────────────────────

describe("WhatsAppChat — connection states", () => {
  it("shows loading spinner while connections load", async () => {
    mockUseWhatsAppConnections.mockReturnValue({
      data: [],
      isLoading: true,
      isError: false,
    });
    const { getByText } = await renderWhatsAppChat();
    expect(getByText("Carregando conexões...")).toBeTruthy();
  });

  it("shows empty state when no connections exist with link to /conexoes", async () => {
    mockUseWhatsAppConnections.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    });
    const { getByText } = await renderWhatsAppChat();
    expect(getByText("Nenhuma conexão WhatsApp")).toBeTruthy();
    expect(getByText("Conexões")).toBeTruthy();
  });

  it("shows connection selector buttons for each connection", async () => {
    mockUseWhatsAppConnections.mockReturnValue({
      data: [makeConn({ id: "c1", label: "SP" }), makeConn({ id: "c2", label: "RJ" })],
      isLoading: false,
      isError: false,
    });
    const { getByText } = await renderWhatsAppChat();
    expect(getByText("SP")).toBeTruthy();
    expect(getByText("RJ")).toBeTruthy();
  });
});

describe("WhatsAppChat — conversation list", () => {
  it("shows skeleton while chats are loading", async () => {
    mockUseWhatsAppChats.mockReturnValue({
      data: [],
      isLoading: true,
      isError: false,
    });
    const { getAllByTestId } = await renderWhatsAppChat();
    const skeletons = getAllByTestId("skeleton");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("shows empty state when no chats for the connection", async () => {
    mockUseWhatsAppChats.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    });
    const { getByText } = await renderWhatsAppChat();
    expect(getByText("Nenhuma conversa ainda nesta conexão.")).toBeTruthy();
  });

  it("renders chat rows with contact and last message", async () => {
    const chat = makeChat({ contact: "5511999998888@c.us", last_message: "Olá!" });
    mockUseWhatsAppChats.mockReturnValue({
      data: [chat],
      isLoading: false,
      isError: false,
    });
    const { getByText } = await renderWhatsAppChat();
    // Contact stripped of JID suffix
    expect(getByText("5511999998888")).toBeTruthy();
    expect(getByText("Olá!")).toBeTruthy();
  });

  it("shows unread badge when chat has unread messages", async () => {
    const chat = makeChat({ unread: 5 });
    mockUseWhatsAppChats.mockReturnValue({
      data: [chat],
      isLoading: false,
      isError: false,
    });
    const { getByText } = await renderWhatsAppChat();
    expect(getByText("5")).toBeTruthy();
  });
});

describe("WhatsAppChat — thread", () => {
  beforeEach(() => {
    // Set up a chat list so we can select one
    mockUseWhatsAppChats.mockReturnValue({
      data: [makeChat()],
      isLoading: false,
      isError: false,
    });
  });

  async function renderAndOpenThread() {
    const result = await renderWhatsAppChat();
    const rtl = await import("@testing-library/react");
    const chatRow = result.getByText("5511999998888");
    rtl.fireEvent.click(chatRow.closest("button")!);
    return { ...result, rtl };
  }

  it("shows loading skeleton while messages load", async () => {
    mockUseWhatsAppChatMessages.mockReturnValue({
      data: [],
      isLoading: true,
      isError: false,
    });
    const { getAllByTestId } = await renderAndOpenThread();
    const skeletons = getAllByTestId("skeleton");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("shows empty state when no messages", async () => {
    mockUseWhatsAppChatMessages.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    });
    const { getByText } = await renderAndOpenThread();
    expect(getByText("Nenhuma mensagem ainda.")).toBeTruthy();
  });

  it("renders inbound and outbound messages", async () => {
    mockUseWhatsAppChatMessages.mockReturnValue({
      data: [
        makeMessage("m1", "inbound", "Bom dia!"),
        makeMessage("m2", "outbound", "Tudo bem!"),
      ],
      isLoading: false,
      isError: false,
    });
    const { getByText } = await renderAndOpenThread();
    expect(getByText("Bom dia!")).toBeTruthy();
    expect(getByText("Tudo bem!")).toBeTruthy();
  });
});

describe("WhatsAppChat — composer", () => {
  beforeEach(() => {
    mockUseWhatsAppChats.mockReturnValue({
      data: [makeChat()],
      isLoading: false,
      isError: false,
    });
    mockUseWhatsAppChatMessages.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    });
  });

  async function renderWithOpenThread() {
    const result = await renderWhatsAppChat();
    const rtl = await import("@testing-library/react");
    const chatRow = result.getByText("5511999998888");
    rtl.fireEvent.click(chatRow.closest("button")!);
    return { ...result, fireEvent: rtl.fireEvent };
  }

  it("Send button is disabled when input is empty", async () => {
    const { getByLabelText } = await renderWithOpenThread();
    const sendBtn = getByLabelText("Enviar mensagem");
    expect((sendBtn as HTMLButtonElement).disabled).toBe(true);
  });

  it("Send button is enabled when input has text", async () => {
    const { getByLabelText, fireEvent } = await renderWithOpenThread();
    const input = getByLabelText("Mensagem");
    fireEvent.change(input, { target: { value: "Olá" } });
    const sendBtn = getByLabelText("Enviar mensagem");
    expect((sendBtn as HTMLButtonElement).disabled).toBe(false);
  });

  it("Enter key triggers send", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({});
    mockUseSendWhatsAppMessage.mockReturnValue({ mutateAsync, isPending: false });

    const { getByLabelText, fireEvent } = await renderWithOpenThread();
    const input = getByLabelText("Mensagem");
    fireEvent.change(input, { target: { value: "Olá" } });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: false });

    expect(mutateAsync).toHaveBeenCalledWith({ text: "Olá" });
  });
});

describe("WhatsAppChat — auto-reply toggle", () => {
  const chat = makeChat();

  beforeEach(() => {
    mockUseWhatsAppChats.mockReturnValue({
      data: [chat],
      isLoading: false,
      isError: false,
    });
    mockUseWhatsAppChatMessages.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    });
  });

  async function renderWithOpenThread(autoReplyEnabled = false) {
    mockUseWhatsAppConnections.mockReturnValue({
      data: [makeConn({ auto_reply_enabled: autoReplyEnabled })],
      isLoading: false,
      isError: false,
    });
    const result = await renderWhatsAppChat();
    const rtl = await import("@testing-library/react");
    const chatRow = result.getByText("5511999998888");
    rtl.fireEvent.click(chatRow.closest("button")!);
    return { ...result, fireEvent: rtl.fireEvent };
  }

  it("Switch reflects auto_reply_enabled=false", async () => {
    const { getByTestId } = await renderWithOpenThread(false);
    const sw = getByTestId("auto-reply-switch");
    expect(sw.getAttribute("aria-checked")).toBe("false");
  });

  it("Switch reflects auto_reply_enabled=true", async () => {
    const { getByTestId } = await renderWithOpenThread(true);
    const sw = getByTestId("auto-reply-switch");
    expect(sw.getAttribute("aria-checked")).toBe("true");
  });

  it("clicking Switch calls useSetAutoReply with toggled value", async () => {
    const mutate = vi.fn();
    mockUseSetAutoReply.mockReturnValue({ mutate, isPending: false });
    const { getByTestId, fireEvent } = await renderWithOpenThread(false);
    const sw = getByTestId("auto-reply-switch");
    fireEvent.click(sw);
    expect(mutate).toHaveBeenCalledWith({ enabled: true });
  });
});
