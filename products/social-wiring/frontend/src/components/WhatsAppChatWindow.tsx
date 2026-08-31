/**
 * WhatsAppChatWindow — embeddable WhatsApp chat surface scoped to ONE connection.
 *
 * Drop-in for any context that already has a connectionId (the MarcaModal
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
 * Data layer (realtime v2): reads are pure Postgres behind keyset pagination
 * and updates arrive over ONE SSE stream per connection. `useWhatsAppRealtime`
 * is mounted HERE, once, because this component owns the connection scope —
 * mounting it deeper (per thread) would open a server-side stream reader per
 * open conversation for identical data.
 */
import { useMemo } from "react";
import {
  useWhatsAppChats,
  useWhatsAppChatMessages,
  useSendWhatsAppMessage,
  useSetAutoReply,
  useMarkChatRead,
  useWhatsAppRealtime,
} from "@/hooks/useWhatsAppChats";
import { ChatWindow, type ChatWindowAdapter } from "@noctusai/lib/design-system";

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * Resolve the display title for a chat.
 * The backend sets `title` = resolved contact name when available, otherwise
 * the raw JID ("5511999998888@c.us"). Strip the JID suffix only when the title
 * still looks like a JID — a real name must never be truncated at an "@".
 */
function displayContact(title: string | null | undefined, chatId: string): string {
  // Defensive: the backend guarantees a non-null title, but one malformed row
  // must never take down the entire conversation list. Fall back through the
  // JID to something renderable rather than throwing inside a .map().
  const raw = title ?? chatId ?? "";
  if (raw.includes("@")) return raw.replace(/@.*$/, "");
  return raw;
}

// ─── WhatsApp adapter ─────────────────────────────────────────────────────────

function useWhatsAppThreadsAdapter(connectionId: string | null) {
  const { data: chats, isPending, isError } = useWhatsAppChats(connectionId);
  return {
    data: (chats ?? []).map((chat) => ({
      id: chat.chat_id,
      title: displayContact(chat.title, chat.chat_id),
      lastMessagePreview: chat.last_message_preview,
      lastMessageAt: chat.last_message_at,
      lastDirection: chat.last_direction,
      unreadCount: chat.unread_count,
    })),
    // `isPending` alone, NOT `isPending || isFetching` — deliberately the
    // opposite of the usual isLoading advice here. ChatWindow's
    // `ChatAsyncResult` (seed/lib/frontend/src/design-system/chat/ChatWindow.tsx)
    // exposes exactly ONE boolean and swaps its whole thread list on it, so
    // this adapter is the only place that can pre-resolve "first load vs.
    // background refetch". `isPending` already means "no data has ever
    // landed for this query key" in TanStack v5 (this hook sets no
    // `placeholderData`), so it stays false through every background
    // refetch/poll once the first page has landed — the conversation list
    // never unmounts back to a skeleton on a realtime update or after a
    // send. (KB § PATTERNS/frontend/lying-loading-state.md)
    isLoading: isPending,
    isError,
  };
}

function useWhatsAppMessagesAdapter(connectionId: string | null, chatId: string | null) {
  const { data: messages, isPending, isError } =
    useWhatsAppChatMessages(connectionId, chatId);
  return {
    data: (messages ?? []).map((m) => ({
      id: m.id,
      direction: m.direction,
      body: m.body || (m.structured_payload ? "[mídia]" : ""),
      created_at: m.created_at,
    })),
    // Same reasoning as useWhatsAppThreadsAdapter above — `isPending` alone.
    // This matters MORE here than for the thread list: unmounting the
    // message panel on every background poll/send also destroys scroll
    // position, so a chat that stayed rendered but silently updated is
    // strictly better than one that flickers to a skeleton and jumps.
    isLoading: isPending,
    isError,
  };
}

function useWhatsAppLoadMoreAdapter(connectionId: string | null, chatId: string | null) {
  const { hasNextPage, isFetchingNextPage, fetchNextPage } =
    useWhatsAppChatMessages(connectionId, chatId);
  return {
    hasMore: !!hasNextPage,
    isLoadingMore: isFetchingNextPage,
    loadMore: () => { void fetchNextPage(); },
  };
}

/**
 * ⚠️ markRead reaches the user's REAL phone: the backend fires WAHA `sendSeen`
 * in the background, so opening a chat here marks it read on the device too.
 * That is intended and user-approved. The organ calls this exactly once per
 * opened thread — never on hover or prefetch.
 */
function useWhatsAppReadStateAdapter(connectionId: string | null) {
  const markRead = useMarkChatRead(connectionId);
  return {
    markRead: (chatId: string) => markRead.mutate({ chatId }),
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
    useLoadMore: useWhatsAppLoadMoreAdapter,
    useReadState: useWhatsAppReadStateAdapter,
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
  // ONE stream per connection, owned here. Every hook in useWhatsAppChats reads
  // the caches this maintains; nothing below needs to know a transport exists.
  useWhatsAppRealtime(connectionId);

  // Rebuilding the adapter each render would give ChatWindow a new object
  // identity every time, which is exactly the kind of churn that makes hook
  // identity in an adapter bag fragile.
  const adapter = useMemo(
    () => buildWhatsAppAdapter(autoReplyEnabled),
    [autoReplyEnabled],
  );

  return (
    <ChatWindow
      scopeId={connectionId}
      adapter={adapter}
      emptyThreadsLabel="Nenhuma conversa nesta conexão."
      className={className}
    />
  );
}

export default WhatsAppChatWindow;
