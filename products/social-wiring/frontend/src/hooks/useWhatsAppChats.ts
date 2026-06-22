/**
 * WhatsApp chat hooks — conversation list, message thread, send, auto-reply.
 *
 * Polling v1 design: all live-read logic lives HERE. The poll intervals are
 * encapsulated behind these hooks so a WebSocket v2 upgrade only touches
 * hook internals — callers never see the transport.
 *
 * Query key shape:
 *   ["whatsapp","connections",connId,"chats"]
 *   ["whatsapp","connections",connId,"chats",chatId,"messages"]
 *
 * Backend contract (built in parallel):
 *   GET  /api/whatsapp/connections/{connId}/chats
 *   GET  /api/whatsapp/connections/{connId}/chats/{chatId}/messages?limit=50
 *   POST /api/whatsapp/connections/{connId}/chats/{chatId}/send   body: { text }
 *   PUT  /api/whatsapp/connections/{connId}/auto-reply            body: { enabled }
 *
 * chatId values are WhatsApp JIDs (e.g. "5511999998888@c.us") — MUST be
 * URL-encoded in path segments because of the "@" character.
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

const CONN_BASE = "/api/whatsapp/connections";
const CONN_KEY = ["whatsapp", "connections"] as const;

// ─── Types ───────────────────────────────────────────────────────────────────

/** Summary row shown in the conversation list (left panel). */
export interface ChatSummary {
  chat_id: string;
  contact: string;
  last_message: string;
  /** ISO datetime string */
  last_message_at: string;
  last_direction: "inbound" | "outbound";
  unread: number;
}

/** Full message in the thread (right panel). */
export interface Message {
  id: string;
  chat_id: string;
  direction: "inbound" | "outbound";
  body: string;
  /** ISO datetime string */
  created_at: string;
  provider_message_id: string | null;
  /** Arbitrary media/structured payload — shown as fallback when body is empty. */
  structured_payload: Record<string, unknown> | null;
}

/** Result from PUT /auto-reply */
export interface AutoReplyResult {
  connection_id: string;
  auto_reply_enabled: boolean;
}

// ─── Conversation list ────────────────────────────────────────────────────────

/**
 * Live conversation list for one connection. Polls every 5 s (v1 seam).
 * Disabled when connId is null so callers can pass the selected-connection id
 * directly without an additional enabled guard.
 *
 * WS-v2 seam: replace `refetchInterval` with a socket subscription that calls
 * `qc.setQueryData([...chatKey], updater)` — the hook signature stays identical.
 */
export function useWhatsAppChats(connId: string | null) {
  return useQuery<ChatSummary[]>({
    queryKey: [...CONN_KEY, connId, "chats"],
    queryFn: () =>
      api.get<ChatSummary[]>(`${CONN_BASE}/${connId}/chats`),
    enabled: !!connId,
    refetchInterval: 5000,
  });
}

// ─── Message thread ───────────────────────────────────────────────────────────

/**
 * Live message thread for one chat within one connection. Polls every 3 s.
 * Messages are returned oldest-first from the backend.
 *
 * WS-v2 seam: replace `refetchInterval` with per-chat socket subscription;
 * the hook signature and key stay identical.
 */
export function useWhatsAppChatMessages(
  connId: string | null,
  chatId: string | null,
) {
  return useQuery<Message[]>({
    queryKey: [...CONN_KEY, connId, "chats", chatId, "messages"],
    queryFn: () =>
      api.get<Message[]>(
        `${CONN_BASE}/${connId}/chats/${encodeURIComponent(chatId!)}/messages?limit=50`,
      ),
    enabled: !!connId && !!chatId,
    refetchInterval: 3000,
  });
}

// ─── Send message ─────────────────────────────────────────────────────────────

/**
 * Mutation to send a message to an open chat.
 * On success invalidates the thread messages + the conversation list so both
 * update immediately without waiting for the next poll cycle.
 */
export function useSendWhatsAppMessage(
  connId: string | null,
  chatId: string | null,
) {
  const qc = useQueryClient();

  return useMutation<Message, unknown, { text: string }>({
    mutationFn: ({ text }) =>
      api.post<Message>(
        `${CONN_BASE}/${connId}/chats/${encodeURIComponent(chatId!)}/send`,
        { text },
      ),
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: [...CONN_KEY, connId, "chats", chatId, "messages"],
      });
      qc.invalidateQueries({ queryKey: [...CONN_KEY, connId, "chats"] });
    },
  });
}

// ─── Auto-reply toggle ────────────────────────────────────────────────────────

/**
 * Mutation to enable/disable AI auto-reply for a connection.
 * On success invalidates the connections list so the toggle reflects the new
 * `auto_reply_enabled` value from the server without a manual refresh.
 */
export function useSetAutoReply(connId: string | null) {
  const qc = useQueryClient();

  return useMutation<AutoReplyResult, unknown, { enabled: boolean }>({
    mutationFn: ({ enabled }) =>
      api.put<AutoReplyResult>(`${CONN_BASE}/${connId}/auto-reply`, {
        enabled,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CONN_KEY });
    },
  });
}
