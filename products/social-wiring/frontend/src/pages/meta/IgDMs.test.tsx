/**
 * IgDMs.test.tsx — Instagram "DMs" minimal 2-pane subtab.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const mockUseActiveMetaAccountId = vi.fn();
const mockUseIgConversations = vi.fn();
const mockUseIgMessages = vi.fn();
const mockUseSendIgMessage = vi.fn();

vi.mock("@/hooks/useMeta", () => ({
  isAppReviewGate: (x: unknown) =>
    !!x && typeof x === "object" && (x as any).requires_app_review === true,
  useActiveMetaAccountId: mockUseActiveMetaAccountId,
  useIgConversations: mockUseIgConversations,
  useIgMessages: mockUseIgMessages,
  useSendIgMessage: mockUseSendIgMessage,
}));

vi.mock("@/components/ui/card", () => ({
  Card: ({ children, ...p }: any) => <div {...p}>{children}</div>,
  CardContent: ({ children, ...p }: any) => <div {...p}>{children}</div>,
}));
vi.mock("@/components/ui/button", () => ({
  Button: ({ children, ...p }: any) => <button {...p}>{children}</button>,
}));
vi.mock("@/components/ui/input", () => ({
  Input: (p: any) => <input {...p} />,
}));
vi.mock("@/components/ui/skeleton", () => ({
  Skeleton: ({ "data-testid": dt }: any) => <div data-testid={dt ?? "skeleton"} />,
}));
vi.mock("lucide-react", () => ({
  CircleAlert: () => <span data-testid="icon-alert" />,
  Loader2: () => null,
  MessageCircle: () => null,
  Send: () => null,
  ShieldAlert: () => null,
}));

const noopMutation = () => ({ mutate: vi.fn(), isPending: false, data: undefined });

function setDefaults() {
  mockUseActiveMetaAccountId.mockReturnValue("acc-1");
  mockUseIgConversations.mockReturnValue({
    data: { conversations: [] },
    isLoading: false,
    isError: false,
  });
  mockUseIgMessages.mockReturnValue({ data: { messages: [] }, isLoading: false, isError: false });
  mockUseSendIgMessage.mockReturnValue(noopMutation());
}

beforeEach(() => setDefaults());

async function renderPage() {
  const React = (await import("react")).default;
  const { default: IgDMs } = await import("./IgDMs");
  const rtl = await import("@testing-library/react");
  return { ...rtl.render(React.createElement(IgDMs)), fireEvent: rtl.fireEvent };
}

describe("IgDMs — no account selected", () => {
  it("shows the select-an-account prompt", async () => {
    mockUseActiveMetaAccountId.mockReturnValue(null);
    const { getByTestId } = await renderPage();
    expect(getByTestId("ig-dm-no-account")).toBeTruthy();
  });
});

describe("IgDMs — conversation list states", () => {
  it("renders a loading state", async () => {
    mockUseIgConversations.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    const { getByTestId } = await renderPage();
    expect(getByTestId("ig-dm-list-loading")).toBeTruthy();
  });

  it("renders an error state", async () => {
    mockUseIgConversations.mockReturnValue({ data: undefined, isLoading: false, isError: true });
    const { getByTestId } = await renderPage();
    expect(getByTestId("ig-dm-list-error")).toBeTruthy();
  });

  it("renders an empty state", async () => {
    const { getByTestId } = await renderPage();
    expect(getByTestId("ig-dm-list-empty")).toBeTruthy();
  });

  it("renders a 'select a conversation' placeholder when none selected", async () => {
    mockUseIgConversations.mockReturnValue({
      data: {
        conversations: [
          { id: "c1", participant_name: "Fulano", participant_id: "u1", updated_time: null, snippet: "oi", unread_count: 0 },
        ],
      },
      isLoading: false,
      isError: false,
    });
    const { getByTestId } = await renderPage();
    expect(getByTestId("ig-dm-list")).toBeTruthy();
    expect(getByTestId("ig-dm-no-selection")).toBeTruthy();
  });
});

describe("IgDMs — thread + send", () => {
  it("selects a conversation, shows the empty thread, and sends a message", async () => {
    mockUseIgConversations.mockReturnValue({
      data: {
        conversations: [
          { id: "c1", participant_name: "Fulano", participant_id: "u1", updated_time: null, snippet: "oi", unread_count: 0 },
        ],
      },
      isLoading: false,
      isError: false,
    });
    const send = vi.fn();
    mockUseSendIgMessage.mockReturnValue({ mutate: send, isPending: false, data: undefined });

    const { getByTestId, fireEvent } = await renderPage();
    fireEvent.click(getByTestId("ig-dm-conversation-c1"));
    expect(getByTestId("ig-dm-thread-empty")).toBeTruthy();

    fireEvent.change(getByTestId("ig-dm-send-input"), { target: { value: "olá" } });
    fireEvent.submit(getByTestId("ig-dm-send-form"));
    expect(send).toHaveBeenCalledWith({ recipient_id: "u1", text: "olá" }, expect.anything());
  });

  it("shows the App Review gate when sending is gated", async () => {
    mockUseIgConversations.mockReturnValue({
      data: {
        conversations: [
          { id: "c1", participant_name: "Fulano", participant_id: "u1", updated_time: null, snippet: "oi", unread_count: 0 },
        ],
      },
      isLoading: false,
      isError: false,
    });
    mockUseSendIgMessage.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      data: { requires_app_review: true, error: "Escopo pendente" },
    });
    const { getByTestId, fireEvent } = await renderPage();
    fireEvent.click(getByTestId("ig-dm-conversation-c1"));
    expect(getByTestId("meta-app-review-gate")).toBeTruthy();
  });
});
