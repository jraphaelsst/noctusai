/**
 * WhatsAppChatWindow.tsx — unit tests for the WhatsApp adapter wired onto the
 * shared seed `<ChatWindow>` organ.
 *
 * `@noctusai/lib/design-system` is stubbed at the test boundary (same
 * pattern used across this product's test suite) — the real barrel transitively imports
 * `useAIOutputFor` → `@noctusai/seed/infra`, which throws at module-load
 * time without `VITE_SUPABASE_URL` in the test env. The stub captures the
 * `adapter`/`scopeId` props passed to `<ChatWindow>` so this file asserts
 * the WhatsApp → ChatWindow DTO mapping in isolation, not ChatWindow's own
 * rendering (covered by `seed/lib/frontend/src/design-system/chat/ChatWindow.test.tsx`).
 *
 * Coverage:
 *   1. scopeId + emptyThreadsLabel forwarded correctly
 *   2. useThreads adapter — maps ChatSummary → ChatThread (incl. JID stripping)
 *   3. useMessages adapter — maps Message → ChatMessage (incl. media fallback)
 *   4. useSend adapter — forwards {text} to useSendWhatsAppMessage.mutateAsync
 *   5. useAutoReply adapter — reflects the initial prop + calls useSetAutoReply.mutate
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

// ─── Hook mocks ────────────────────────────────────────────────────────────

const mockUseWhatsAppChats = vi.fn();
const mockUseWhatsAppChatMessages = vi.fn();
const mockUseSendWhatsAppMessage = vi.fn();
const mockUseSetAutoReply = vi.fn();
const mockUseMarkChatRead = vi.fn();
const mockUseWhatsAppRealtime = vi.fn();

vi.mock("@/hooks/useWhatsAppChats", () => ({
  useWhatsAppChats: mockUseWhatsAppChats,
  useWhatsAppChatMessages: mockUseWhatsAppChatMessages,
  useSendWhatsAppMessage: mockUseSendWhatsAppMessage,
  useSetAutoReply: mockUseSetAutoReply,
  useMarkChatRead: mockUseMarkChatRead,
  useWhatsAppRealtime: mockUseWhatsAppRealtime,
}));

// ─── ChatWindow stub — captures props for adapter assertions ───────────────

let lastProps: any = null;
vi.mock("@noctusai/lib/design-system", () => ({
  ChatWindow: (props: any) => {
    lastProps = props;
    return null;
  },
}));

beforeEach(() => {
  lastProps = null;
  mockUseWhatsAppChats.mockReturnValue({ data: [], isLoading: false, isError: false });
  mockUseWhatsAppChatMessages.mockReturnValue({ data: [], isLoading: false, isError: false });
  mockUseSendWhatsAppMessage.mockReturnValue({ mutateAsync: vi.fn().mockResolvedValue({}), isPending: false });
  mockUseSetAutoReply.mockReturnValue({ mutate: vi.fn(), isPending: false });
  mockUseMarkChatRead.mockReturnValue({ mutate: vi.fn(), isPending: false });
  // The realtime subscription is a side effect, not data — the adapter tests
  // assert cache/DTO mapping, so a no-op stub keeps them transport-agnostic.
  mockUseWhatsAppRealtime.mockReturnValue({ status: "open", lastEventId: null });
});

async function renderWindow(props: Partial<{ connectionId: string; autoReplyEnabled: boolean; className: string }> = {}) {
  const mod = await import("./WhatsAppChatWindow");
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  rtl.render(
    React.createElement(mod.WhatsAppChatWindow, { connectionId: "conn-1", ...props }),
  );
}

describe("WhatsAppChatWindow — ChatWindow wiring", () => {
  it("forwards scopeId + a WhatsApp-specific empty label", async () => {
    await renderWindow({ connectionId: "conn-1", className: "mt-1" });
    expect(lastProps.scopeId).toBe("conn-1");
    expect(lastProps.emptyThreadsLabel).toBe("Nenhuma conversa nesta conexão.");
    expect(lastProps.className).toBe("mt-1");
  });

  it("useThreads adapter maps ChatSummary → ChatThread (strips JID, keeps resolved name)", async () => {
    mockUseWhatsAppChats.mockReturnValue({
      data: [
        {
          chat_id: "5511999998888@c.us",
          title: "5511999998888@c.us",
          last_message_preview: "Olá!",
          last_message_at: "2026-07-01T10:00:00Z",
          last_direction: "inbound",
          unread_count: 3,
          last_read_at: null,
          archived: false,
          pinned: false,
        },
      ],
      isLoading: false,
      isError: false,
    });
    await renderWindow();
    const threads = lastProps.adapter.useThreads("conn-1").data;
    expect(threads).toEqual([
      {
        id: "5511999998888@c.us",
        title: "5511999998888",
        lastMessagePreview: "Olá!",
        lastMessageAt: "2026-07-01T10:00:00Z",
        lastDirection: "inbound",
        unreadCount: 3,
      },
    ]);
  });

  it("useMessages adapter maps Message → ChatMessage, falling back to '[mídia]' for empty body + structured payload", async () => {
    mockUseWhatsAppChatMessages.mockReturnValue({
      data: [
        {
          id: "m1",
          chat_id: "c1",
          direction: "inbound",
          body: "",
          created_at: "2026-07-01T10:00:00Z",
          provider_message_id: null,
          structured_payload: { type: "image" },
        },
      ],
      isLoading: false,
      isError: false,
    });
    await renderWindow();
    const messages = lastProps.adapter.useMessages("conn-1", "c1").data;
    expect(messages).toEqual([
      { id: "m1", direction: "inbound", body: "[mídia]", created_at: "2026-07-01T10:00:00Z" },
    ]);
  });

  it("useSend adapter forwards {text} to useSendWhatsAppMessage.mutateAsync", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({ id: "sent-1" });
    mockUseSendWhatsAppMessage.mockReturnValue({ mutateAsync, isPending: false });
    await renderWindow();
    await lastProps.adapter.useSend("conn-1", "c1").mutateAsync({ text: "Oi" });
    expect(mutateAsync).toHaveBeenCalledWith({ text: "Oi" });
  });

  it("useAutoReply adapter reflects the initial prop and calls useSetAutoReply.mutate on toggle", async () => {
    const mutate = vi.fn();
    mockUseSetAutoReply.mockReturnValue({ mutate, isPending: false });
    await renderWindow({ autoReplyEnabled: true });
    const autoReply = lastProps.adapter.useAutoReply!("conn-1");
    expect(autoReply.enabled).toBe(true);
    autoReply.onToggle(false);
    expect(mutate).toHaveBeenCalledWith({ enabled: false });
  });
});
