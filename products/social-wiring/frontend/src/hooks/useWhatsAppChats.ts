/**
 * WhatsApp chat hooks — conversation list, message thread, send, read-state.
 *
 * REALTIME v2. The v1 design polled: the chat list every 5s and the open thread
 * every 3s, against a backend that merged Postgres with a ~13s WAHA call. Both
 * halves of that are gone. Reads are now pure Postgres behind keyset
 * pagination, and updates arrive over ONE SSE stream per connection that
 * patches the query cache in place.
 *
 * The v1 file carried a comment naming this exact upgrade ("replace
 * refetchInterval with a socket subscription that calls qc.setQueryData") —
 * this is that seam, closed.
 *
 * Query key shape (unchanged, deliberately — the keys were never the problem):
 *   ["whatsapp","connections",connId,"chats"]
 *   ["whatsapp","connections",connId,"chats",chatId,"messages"]
 *
 * Backend contract:
 *   GET  /api/whatsapp/connections/{connId}/chats?limit&before&archived
 *          → { items: ChatSummary[], next_before }         NEWEST-FIRST
 *   GET  /api/whatsapp/connections/{connId}/chats/{chatId}/messages?limit&before
 *          → { items: Message[], next_before }             NEWEST-FIRST
 *   POST /api/whatsapp/connections/{connId}/chats/{chatId}/send   { text }
 *   POST /api/whatsapp/connections/{connId}/chats/{chatId}/read   { up_to_message_id? }
 *   GET  /api/whatsapp/connections/{connId}/stream                (SSE)
 *   PUT  /api/whatsapp/connections/{connId}/auto-reply            { enabled }
 *
 * chatId values are WhatsApp JIDs ("5511999998888@c.us") and MUST be
 * URL-encoded in path segments because of the "@".
 */
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type InfiniteData,
} from "@tanstack/react-query";
import { useCallback, useMemo } from "react";
import { api } from "@noctusai/seed/infra";
import { useRealtimeStream, type RealtimeMessage } from "@noctusai/lib";

const CONN_BASE = "/api/whatsapp/connections";
const CONN_KEY = ["whatsapp", "connections"] as const;

const CHATS_PAGE_SIZE = 30;
const MESSAGES_PAGE_SIZE = 50;

// ─── Types (mirror the backend DTOs exactly — renaming here is a contract bump) ─

/** One conversation, as the list renders it. */
export interface ChatSummary {
  chat_id: string;
  title: string;
  last_message_at: string | null;
  last_message_preview: string;
  last_direction: "inbound" | "outbound" | null;
  unread_count: number;
  last_read_at: string | null;
  archived: boolean;
  pinned: boolean;
}

/** Full message in the thread. */
export interface Message {
  id: string;
  chat_id: string;
  direction: "inbound" | "outbound";
  body: string;
  created_at: string;
  provider_message_id: string | null;
  /** WAHA ack level: -1 error · 0 pending · 1 server · 2 device · 3 read · 4 played. */
  ack: number | null;
  acked_at: string | null;
  structured_payload: Record<string, unknown> | null;
}

interface Page<T> {
  items: T[];
  next_before: string | null;
}

export interface AutoReplyResult {
  connection_id: string;
  auto_reply_enabled: boolean;
}

export interface ChatReadResult {
  chat_id: string;
  unread_count: number;
  last_read_at: string | null;
}

const chatsKey = (connId: string | null) => [...CONN_KEY, connId, "chats"] as const;
const messagesKey = (connId: string | null, chatId: string | null) =>
  [...CONN_KEY, connId, "chats", chatId, "messages"] as const;

// ─── Conversation list ───────────────────────────────────────────────────────

/**
 * Conversation list for one connection.
 *
 * No `refetchInterval`: the SSE stream (see `useWhatsAppRealtime`) patches this
 * cache entry directly. `staleTime: Infinity` is deliberate and load-bearing —
 * once the stream is the source of updates, any background refetch is pure
 * waste AND can clobber a newer stream-applied patch with an older server read.
 */
export function useWhatsAppChats(connId: string | null) {
  const query = useQuery<Page<ChatSummary>>({
    queryKey: chatsKey(connId),
    queryFn: () =>
      api.get<Page<ChatSummary>>(
        `${CONN_BASE}/${connId}/chats?limit=${CHATS_PAGE_SIZE}&archived=false`,
      ),
    enabled: !!connId,
    staleTime: Infinity,
  });

  return {
    ...query,
    /** Flattened for callers; the envelope stays in the cache for patching. */
    data: query.data?.items,
  };
}

// ─── Message thread ──────────────────────────────────────────────────────────

/**
 * Message thread for one chat, paginated backwards through history.
 *
 * The backend returns NEWEST-first (keyset paging reads naturally that way);
 * the UI renders oldest→newest top-to-bottom, so pages are flattened and
 * reversed here. Doing it in the hook keeps the ordering contract in exactly
 * one place instead of leaking into every consumer.
 */
export function useWhatsAppChatMessages(
  connId: string | null,
  chatId: string | null,
) {
  const query = useInfiniteQuery<Page<Message>, Error, InfiniteData<Page<Message>>, readonly unknown[], string | null>({
    queryKey: messagesKey(connId, chatId),
    initialPageParam: null,
    queryFn: ({ pageParam }) => {
      const cursor = pageParam ? `&before=${encodeURIComponent(pageParam)}` : "";
      return api.get<Page<Message>>(
        `${CONN_BASE}/${connId}/chats/${encodeURIComponent(chatId!)}/messages` +
          `?limit=${MESSAGES_PAGE_SIZE}${cursor}`,
      );
    },
    getNextPageParam: (lastPage) => lastPage.next_before,
    enabled: !!connId && !!chatId,
    staleTime: Infinity,
  });

  const messages = useMemo(() => {
    const pages = query.data?.pages ?? [];
    // pages[0] is the newest page; within a page items are newest-first.
    // Oldest-first overall = reverse the page order, then reverse each page.
    return pages
      .slice()
      .reverse()
      .flatMap((p) => p.items.slice().reverse());
  }, [query.data]);

  return { ...query, data: messages };
}

// ─── Send ────────────────────────────────────────────────────────────────────

/**
 * Send to the open chat.
 *
 * No invalidation on success: the server persists the outbound row and the
 * stream delivers it back as `message.new`, which patches both caches. An
 * invalidate here would fire a redundant refetch and race the stream patch.
 */
export function useSendWhatsAppMessage(
  connId: string | null,
  chatId: string | null,
) {
  return useMutation<Message, unknown, { text: string }>({
    mutationFn: ({ text }) =>
      api.post<Message>(
        `${CONN_BASE}/${connId}/chats/${encodeURIComponent(chatId!)}/send`,
        { text },
      ),
  });
}

// ─── Read state ──────────────────────────────────────────────────────────────

/**
 * Mark a chat read.
 *
 * ⚠️ This marks the conversation read on the USER'S REAL PHONE — the backend
 * fires WAHA `sendSeen` in the background. That is intended and user-approved;
 * do not "optimize" it into firing on hover or prefetch.
 *
 * The badge is cleared optimistically so the UI never waits on a round trip;
 * the authoritative `chat.read` event follows over the stream.
 */
export function useMarkChatRead(connId: string | null) {
  const qc = useQueryClient();

  return useMutation<ChatReadResult, unknown, { chatId: string; upToMessageId?: string }>({
    mutationFn: ({ chatId, upToMessageId }) =>
      api.post<ChatReadResult>(
        `${CONN_BASE}/${connId}/chats/${encodeURIComponent(chatId)}/read`,
        upToMessageId ? { up_to_message_id: upToMessageId } : {},
      ),
    onMutate: ({ chatId }) => {
      qc.setQueryData<Page<ChatSummary>>(chatsKey(connId), (prev) =>
        prev
          ? {
              ...prev,
              items: prev.items.map((c) =>
                c.chat_id === chatId ? { ...c, unread_count: 0 } : c,
              ),
            }
          : prev,
      );
    },
  });
}

// ─── Auto-reply ──────────────────────────────────────────────────────────────

export function useSetAutoReply(connId: string | null) {
  const qc = useQueryClient();

  return useMutation<AutoReplyResult, unknown, { enabled: boolean }>({
    mutationFn: ({ enabled }) =>
      api.put<AutoReplyResult>(`${CONN_BASE}/${connId}/auto-reply`, { enabled }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CONN_KEY });
    },
  });
}

// ─── Realtime ────────────────────────────────────────────────────────────────

/**
 * Subscribe one connection's event stream and patch the caches in place.
 *
 * Mount ONCE per connection, high in the tree — every hook above reads the
 * caches this maintains. Mounting it twice opens two server-side stream
 * readers for identical data.
 *
 * Every handler is idempotent: a resumed stream can redeliver an event the
 * client already applied, so "insert if absent, replace if present" is the
 * rule throughout rather than blind append.
 */
export function useWhatsAppRealtime(connId: string | null) {
  const qc = useQueryClient();

  const onEvent = useCallback(
    (evt: RealtimeMessage) => {
      const p = evt.payload as Record<string, any>;

      switch (evt.event) {
        case "message.new": {
          const chatId: string | undefined = p.chat_id;
          const message: Message | undefined = p.message;
          if (!chatId || !message) return;

          qc.setQueryData<InfiniteData<Page<Message>>>(
            messagesKey(connId, chatId),
            (prev) => {
              if (!prev || prev.pages.length === 0) return prev;
              const already = prev.pages.some((pg) =>
                pg.items.some((m) => m.id === message.id),
              );
              if (already) return prev;
              // pages[0] holds the newest window; newest-first within it.
              const [newest, ...rest] = prev.pages;
              return {
                ...prev,
                pages: [{ ...newest, items: [message, ...newest.items] }, ...rest],
              };
            },
          );
          break;
        }

        case "message.ack": {
          const chatId: string | undefined = p.chat_id;
          if (!chatId) return;
          qc.setQueryData<InfiniteData<Page<Message>>>(
            messagesKey(connId, chatId),
            (prev) =>
              prev
                ? {
                    ...prev,
                    pages: prev.pages.map((pg) => ({
                      ...pg,
                      items: pg.items.map((m) =>
                        m.provider_message_id === p.provider_message_id
                          ? { ...m, ack: p.ack ?? m.ack, acked_at: p.acked_at ?? m.acked_at }
                          : m,
                      ),
                    })),
                  }
                : prev,
          );
          break;
        }

        case "chat.upsert":
        case "chat.read": {
          const incoming = p as Partial<ChatSummary> & { chat_id?: string };
          if (!incoming.chat_id) return;
          qc.setQueryData<Page<ChatSummary>>(chatsKey(connId), (prev) => {
            if (!prev) return prev;
            const idx = prev.items.findIndex((c) => c.chat_id === incoming.chat_id);
            const merged =
              idx >= 0
                ? { ...prev.items[idx], ...incoming }
                : (incoming as ChatSummary);
            const rest = idx >= 0 ? prev.items.filter((_, i) => i !== idx) : prev.items;
            // Re-sort rather than assuming position: an upsert usually moves a
            // chat to the top, but chat.read does not reorder anything.
            const items = [merged, ...rest].sort((a, b) =>
              (b.last_message_at ?? "").localeCompare(a.last_message_at ?? ""),
            );
            return { ...prev, items };
          });
          break;
        }

        case "session.status": {
          // Patch the status cache the QR panel reads — this is what lets the
          // pairing screen stop polling entirely.
          qc.setQueryData([...CONN_KEY, connId, "status"], (prev: any) => ({
            ...(prev ?? {}),
            connection_id: connId,
            status: p.status,
            paired: p.paired ?? prev?.paired ?? false,
          }));
          // A status change is exactly when a QR appears or stops being valid.
          qc.invalidateQueries({ queryKey: [...CONN_KEY, connId, "qr"] });
          break;
        }

        default:
          break;
      }
    },
    [qc, connId],
  );

  return useRealtimeStream(connId ? `${CONN_BASE}/${connId}/stream` : null, {
    onEvent,
  });
}
