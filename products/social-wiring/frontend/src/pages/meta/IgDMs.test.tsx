/**
 * IgDMs.test.tsx — Instagram "DMs" subtab, now a thin Meta-DM adapter over
 * the shared seed `<ChatWindow>` organ.
 *
 * `@noctusai/lib/design-system` is stubbed at the test boundary (same
 * pattern as `WhatsAppChatWindow.test.tsx`) — the
 * real barrel transitively imports `useAIOutputFor` → `@noctusai/seed/infra`,
 * which throws at module-load time without `VITE_SUPABASE_URL`. The stub
 * captures the `scopeId`/`adapter` props so this file asserts the Meta DM →
 * ChatWindow DTO mapping in isolation — ChatWindow's own rendering states
 * (loading/error/empty/success/composer/gate-banner) are covered by
 * `seed/lib/frontend/src/design-system/chat/ChatWindow.test.tsx`.
 *
 * Coverage:
 *   1. No account selected — the select-an-account prompt
 *   2. scopeId + emptyThreadsLabel forwarded correctly
 *   3. useThreads adapter — maps IGConversation → ChatThread
 *   4. useMessages adapter — maps IGMessage → ChatMessage
 *   5. useSend adapter — resolves recipient_id from the conversation list,
 *      forwards {recipient_id, text} to useSendIgMessage
 *   6. useSend adapter — throws when no recipient_id can be resolved
 *   7. useSend adapter — App Review gate surfaces as a thrown Error (never a fake success)
 *   8. adapter has NO useAutoReply — Wave 3 has no AI-reply toggle for IG DMs
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
  isMetaSetupGate: (x: unknown) =>
    !!x && typeof x === "object" && (x as any).requires_setup === true,
  useActiveMetaAccountId: mockUseActiveMetaAccountId,
  useIgConversations: mockUseIgConversations,
  useIgMessages: mockUseIgMessages,
  useSendIgMessage: mockUseSendIgMessage,
}));

let lastProps: any = null;
vi.mock("@noctusai/lib/design-system", () => ({
  ChatWindow: (props: any) => {
    lastProps = props;
    return null;
  },
}));

beforeEach(() => {
  lastProps = null;
  mockUseActiveMetaAccountId.mockReturnValue("acc-1");
  mockUseIgConversations.mockReturnValue({ data: { conversations: [] }, isLoading: false, isError: false });
  mockUseIgMessages.mockReturnValue({ data: { messages: [] }, isLoading: false, isError: false });
  mockUseSendIgMessage.mockReturnValue({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false, data: undefined });
});

async function renderPage() {
  const React = (await import("react")).default;
  const { default: IgDMs } = await import("./IgDMs");
  const rtl = await import("@testing-library/react");
  return { ...rtl.render(React.createElement(IgDMs)) };
}

describe("IgDMs — no account selected", () => {
  it("shows the select-an-account prompt", async () => {
    mockUseActiveMetaAccountId.mockReturnValue(null);
    const { getByTestId } = await renderPage();
    expect(getByTestId("ig-dm-no-account")).toBeTruthy();
  });
});

describe("IgDMs — Meta setup gate", () => {
  it("renders the actionable setup notice (not ChatWindow) when the app lacks the messaging capability", async () => {
    // Graph #3 → backend returns `{requires_setup: true}` (200). The tab
    // must show the actionable card, NOT an empty ChatWindow that would
    // misread as "no conversations" and NOT a 502 error toast.
    mockUseIgConversations.mockReturnValue({
      data: { requires_setup: true, error: "Application does not have the capability" },
      isLoading: false,
      isError: false,
    });
    const { getByTestId } = await renderPage();
    expect(getByTestId("meta-setup-gate")).toBeTruthy();
    expect(lastProps).toBeNull(); // ChatWindow never rendered
  });
});

describe("IgDMs — demo mode (App-Review screencast)", () => {
  afterEach(() => {
    window.history.pushState({}, "", "/");
  });

  it("`?demo=1` renders the seeded demo ChatWindow (no live account/gate needed)", async () => {
    window.history.pushState({}, "", "/?demo=1");
    // No account, and the conversations hook would gate — demo mode must
    // bypass both and drive ChatWindow from the seeded in-memory adapter.
    mockUseActiveMetaAccountId.mockReturnValue(null);
    const { getByTestId } = await renderPage();
    expect(getByTestId("ig-dm-demo")).toBeTruthy();
    expect(lastProps.scopeId).toBe("demo");
    expect(typeof lastProps.adapter.useThreads).toBe("function");
  });
});

describe("IgDMs — Advanced Access gate", () => {
  it("renders the App-Review notice (not ChatWindow) when the conversations read is advanced-access-gated", async () => {
    // Standard-Access `instagram_manage_messages` on a busy inbox → the
    // backend maps the expired query to `{requires_app_review: true}` (200).
    // The tab must show the actionable notice, NOT an infinite ChatWindow
    // skeleton that would misread as "no conversations".
    mockUseIgConversations.mockReturnValue({
      data: {
        requires_app_review: true,
        error: "As mensagens diretas do Instagram exigem Acesso Avançado à permissão instagram_manage_messages",
      },
      isLoading: false,
      isError: false,
    });
    const { getByTestId } = await renderPage();
    expect(getByTestId("meta-app-review-gate")).toBeTruthy();
    expect(lastProps).toBeNull(); // ChatWindow never rendered
  });
});

describe("IgDMs — ChatWindow wiring", () => {
  it("forwards scopeId + a Meta-DM-specific empty label", async () => {
    await renderPage();
    expect(lastProps.scopeId).toBe("acc-1");
    expect(lastProps.emptyThreadsLabel).toBe("Nenhuma conversa por enquanto.");
  });

  it("useThreads adapter maps IGConversation → ChatThread", async () => {
    mockUseIgConversations.mockReturnValue({
      data: {
        conversations: [
          { id: "c1", participant_name: "Fulano", participant_id: "u1", updated_time: "2026-07-01T10:00:00Z", snippet: "oi", unread_count: 2 },
        ],
      },
      isLoading: false,
      isError: false,
    });
    await renderPage();
    const threads = lastProps.adapter.useThreads("acc-1").data;
    expect(threads).toEqual([
      { id: "c1", title: "Fulano", lastMessagePreview: "oi", lastMessageAt: "2026-07-01T10:00:00Z", unreadCount: 2 },
    ]);
  });

  it("useThreads adapter falls back to 'Contato' when participant_name is null", async () => {
    mockUseIgConversations.mockReturnValue({
      data: {
        conversations: [
          { id: "c1", participant_name: null, participant_id: "u1", updated_time: null, snippet: null, unread_count: 0 },
        ],
      },
      isLoading: false,
      isError: false,
    });
    await renderPage();
    expect(lastProps.adapter.useThreads("acc-1").data[0].title).toBe("Contato");
  });

  it("useMessages adapter maps IGMessage → ChatMessage", async () => {
    mockUseIgMessages.mockReturnValue({
      data: { messages: [{ id: "m1", from_id: "u1", direction: "inbound", text: "Bom dia!", created_at: "2026-07-01T10:00:00Z" }] },
      isLoading: false,
      isError: false,
    });
    await renderPage();
    const messages = lastProps.adapter.useMessages("acc-1", "c1").data;
    expect(messages).toEqual([
      { id: "m1", direction: "inbound", body: "Bom dia!", created_at: "2026-07-01T10:00:00Z" },
    ]);
  });

  it("useSend adapter resolves recipient_id from the conversation list and forwards {recipient_id, text}", async () => {
    mockUseIgConversations.mockReturnValue({
      data: { conversations: [{ id: "c1", participant_name: "Fulano", participant_id: "u1", updated_time: null, snippet: null, unread_count: 0 }] },
      isLoading: false,
      isError: false,
    });
    const mutateAsync = vi.fn().mockResolvedValue({ id: "msg-1" });
    mockUseSendIgMessage.mockReturnValue({ mutate: vi.fn(), mutateAsync, isPending: false, data: undefined });
    await renderPage();
    await lastProps.adapter.useSend("acc-1", "c1").mutateAsync({ text: "olá" });
    expect(mutateAsync).toHaveBeenCalledWith({ recipient_id: "u1", text: "olá" });
  });

  it("useSend adapter throws when the conversation has no resolvable recipient_id", async () => {
    mockUseIgConversations.mockReturnValue({
      data: { conversations: [{ id: "c1", participant_name: "Fulano", participant_id: null, updated_time: null, snippet: null, unread_count: 0 }] },
      isLoading: false,
      isError: false,
    });
    await renderPage();
    await expect(lastProps.adapter.useSend("acc-1", "c1").mutateAsync({ text: "olá" })).rejects.toThrow(
      "Não foi possível identificar o destinatário desta conversa.",
    );
  });

  it("useSend adapter turns an App Review gate response into a thrown Error — never a fake success", async () => {
    mockUseIgConversations.mockReturnValue({
      data: { conversations: [{ id: "c1", participant_name: "Fulano", participant_id: "u1", updated_time: null, snippet: null, unread_count: 0 }] },
      isLoading: false,
      isError: false,
    });
    const mutateAsync = vi.fn().mockResolvedValue({ requires_app_review: true, error: "Escopo pendente" });
    mockUseSendIgMessage.mockReturnValue({ mutate: vi.fn(), mutateAsync, isPending: false, data: undefined });
    await renderPage();
    await expect(lastProps.adapter.useSend("acc-1", "c1").mutateAsync({ text: "olá" })).rejects.toThrow(
      "Escopo pendente",
    );
  });

  it("adapter omits useAutoReply — Wave 3 has no AI-reply toggle for Instagram DMs", async () => {
    await renderPage();
    expect(lastProps.adapter.useAutoReply).toBeUndefined();
  });
});
