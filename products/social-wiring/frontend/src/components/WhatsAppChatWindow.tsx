/**
 * WhatsAppChatWindow — embeddable WhatsApp chat surface scoped to ONE connection.
 *
 * Drop-in for any context that already has a connectionId (the ClienteModal
 * Chat tab, a future inline panel, etc.). It does NOT contain a connection
 * picker — that's the caller's responsibility.
 *
 * Thin WhatsApp adapter over the seed `<ChatWindow>` organ
 * (`@noctusai/lib/design-system`) — all 2-pane rendering (thread list /
 * thread panel / composer / skeletons / empty / error) lives there now.
 * This file's only job is normalizing the WAHA-shaped DTOs (`ChatSummary`,
 * `Message` from `useWhatsAppChats`) into ChatWindow's generic
 * `ChatThread` / `ChatMessage` shape, plus wiring send + the auto-reply
 * toggle. Public props/behaviour are unchanged from the pre-extraction
 * version (connectionId / autoReplyEnabled / className).
 *
 * Data layer: same hooks as before (useWhatsAppChats, useWhatsAppChatMessages,
 * useSendWhatsAppMessage, useSetAutoReply) — the WS-v2 upgrade seam described
 * in those hooks is unaffected by this refactor.
 */
import {
  useWhatsAppChats,
  useWhatsAppChatMessages,
  useSendWhatsAppMessage,
  useSetAutoReply,
} from "@/hooks/useWhatsAppChats";
import { ChatWindow, type ChatWindowAdapter } from "@noctusai/lib/design-system";

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * Resolve the display title for a chat.
 * The backend sets `contact` = resolved name (e.g. "João Raphael") when
 * available, otherwise the raw JID (e.g. "5511999998888@c.us"). Strip the
 * JID suffix only when the contact looks like a JID.
 */
function displayContact(contact: string): string {
  if (contact.includes("@")) return contact.replace(/@.*$/, "");
  return contact;
}

// ─── WhatsApp adapter ─────────────────────────────────────────────────────────

function useWhatsAppThreadsAdapter(connectionId: string | null) {
  const { data: chats, isLoading, isError } = useWhatsAppChats(connectionId);
  return {
    data: (chats ?? []).map((chat) => ({
      id: chat.chat_id,
      title: displayContact(chat.contact),
      lastMessagePreview: chat.last_message,
      lastMessageAt: chat.last_message_at,
      lastDirection: chat.last_direction,
      unreadCount: chat.unread,
    })),
    isLoading,
    isError,
  };
}

function useWhatsAppMessagesAdapter(connectionId: string | null, chatId: string | null) {
  const { data: messages, isLoading, isError } = useWhatsAppChatMessages(connectionId, chatId);
  return {
    data: (messages ?? []).map((m) => ({
      id: m.id,
      direction: m.direction,
      body: m.body || (m.structured_payload ? "[mídia]" : ""),
      created_at: m.created_at,
    })),
    isLoading,
    isError,
  };
}

function useWhatsAppSendAdapter(connectionId: string | null, chatId: string | null) {
  const sendMutation = useSendWhatsAppMessage(connectionId, chatId);
  return {
    mutateAsync: ({ text }: { text: string }) => sendMutation.mutateAsync({ text }),
    isPending: sendMutation.isPending,
  };
}

function useWhatsAppAutoReplyAdapter(connectionId: string | null, autoReplyEnabled: boolean) {
  const autoReplyMutation = useSetAutoReply(connectionId);
  return {
    enabled: autoReplyEnabled,
    isPending: autoReplyMutation.isPending,
    onToggle: (enabled: boolean) => autoReplyMutation.mutate({ enabled }),
  };
}

function buildWhatsAppAdapter(autoReplyEnabled: boolean): ChatWindowAdapter {
  return {
    useThreads: useWhatsAppThreadsAdapter,
    useMessages: useWhatsAppMessagesAdapter,
    useSend: useWhatsAppSendAdapter,
    useAutoReply: (connectionId) => useWhatsAppAutoReplyAdapter(connectionId, autoReplyEnabled),
  };
}

// ─── Main component ───────────────────────────────────────────────────────────

interface WhatsAppChatWindowProps {
  /** WAHA connection ID to show chats for. */
  connectionId: string;
  /** Initial auto-reply state from the parent's connection object. */
  autoReplyEnabled?: boolean;
  className?: string;
}

export function WhatsAppChatWindow({
  connectionId,
  autoReplyEnabled = false,
  className,
}: WhatsAppChatWindowProps) {
  return (
    <ChatWindow
      scopeId={connectionId}
      adapter={buildWhatsAppAdapter(autoReplyEnabled)}
      emptyThreadsLabel="Nenhuma conversa nesta conexão."
      className={className}
    />
  );
}

export default WhatsAppChatWindow;
