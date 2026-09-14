/**
 * Julia chat adapter — contract §E.2 (conversations/messages), §E.3 (SSE,
 * revised 2026-09-14), §E.7 (ChatWindow seams).
 *
 * Wires the seed `<ChatWindow>` organ (`@noctusai/lib/design-system`) onto
 * `/api/conversations`. Mirrors the shape of
 * `products/social-wiring/frontend/src/hooks/useWhatsAppChats.ts` (REST +
 * ONE SSE stream per open scope patches the TanStack cache — no
 * `refetchInterval`), with one structural difference: the WhatsApp stream is
 * scoped to a CONNECTION (patches the whole thread list), Julia's stream is
 * scoped to a single CONVERSATION (`/api/conversations/{id}/stream`,
 * contract §E.3 "Scope"). So the realtime subscription is mounted inside
 * `useJuliaMessagesAdapter`, which `ChatWindow`'s `ThreadPanel` already
 * calls exactly once per opened thread (`key={thread.id}` — see
 * `ChatWindow.tsx`), not at the top `useThreads` level.
 *
 * ── Rendering model (contract §E.3 "Frontend rendering rule", revised
 * 2026-09-14) — replaces the earlier `__live__` scaffold that built blocks
 * from granular `tool.*`/`approval.*` events and vanished at turn end:
 *   - Messages and their `blocks` render ONLY from `message.new` /
 *     `message.updated`, upserted by `id` into the messages cache.
 *     `message.updated` re-publishes the FULL row every time `blocks`
 *     changes, so it is the single source of truth for card state —
 *     durable across a reopen, never cleared at turn end.
 *   - A transient streaming bubble (`id: "__live__"`) is driven only by
 *     `message.delta` and `session.status: "pensando"`. It never holds
 *     blocks, and it is cleared the moment an assistant `message.new`
 *     lands, or `session.status` leaves `"pensando"`.
 *   - `approval.requested` / `approval.resolved` no longer build blocks —
 *     they only invalidate the approvals list query (`useApprovals.ts`'s
 *     `["agents", "approvals", ...]`), so `/aprovacoes` and any other open
 *     surface stay in sync.
 *   - When `session.status` leaves `"pensando"`, the client invalidates the
 *     conversation's messages query once, reconciling anything missed
 *     during a reconnect.
 */
import { useCallback, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/errors";
import { getAuthToken } from "@noctusai/seed/infra";
import { useRealtimeStream, type RealtimeMessage } from "@noctusai/lib";
import type {
  ChatBlock,
  ChatMessage,
  ChatThread,
  ChatWindowAdapter,
} from "@noctusai/lib/design-system";

// ─── Wire types (mirror app/schemas/agents.py) ─────────────────────────────

export interface RawConversation {
  id: string;
  agent_id: string;
  owner_user_id: string;
  titulo: string | null;
  sdk_session_id: string | null;
  status: string;
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface RawMessage {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system";
  texto: string;
  blocks: ChatBlock[];
  token_usage: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

interface Envelope<T> {
  items: T[];
  total: number;
}

/** Every event name contract §E.3 defines. The `events` list passed to
 * `useRealtimeStream` MUST name every one, or the seed transport silently
 * drops it (`seed/lib/frontend/src/realtime.ts` — "load-bearing"). Revised
 * 2026-09-14: `message.updated` is now load-bearing (it is the source of
 * truth for `blocks`) and MUST be included. */
export const JULIA_STREAM_EVENTS = [
  "message.new",
  "message.updated",
  "message.delta",
  "tool.started",
  "tool.finished",
  "approval.requested",
  "approval.resolved",
  "session.status",
  "conversation.upsert",
] as const;

const CONVERSATIONS_KEY = ["agents", "julia", "conversations"] as const;
const messagesKey = (conversationId: string | null) =>
  [...CONVERSATIONS_KEY, conversationId, "messages"] as const;
/** Prefix shared with `useApprovals.ts`'s `APPROVALS_KEY`
 * (`["agents", "approvals", "pendente"]`) — invalidating the prefix covers
 * every filtered view. */
const APPROVALS_KEY_PREFIX = ["agents", "approvals"] as const;

const LIVE_ID = "__live__";

// ─── Mapping helpers ────────────────────────────────────────────────────────

function toChatThread(c: RawConversation): ChatThread {
  return {
    id: c.id,
    title: c.titulo || "Nova conversa",
    lastMessageAt: c.last_message_at,
  };
}

function toChatMessage(m: RawMessage): ChatMessage {
  return {
    id: m.id,
    direction: m.role === "user" ? "outbound" : "inbound",
    body: m.texto,
    created_at: m.created_at,
    blocks: m.blocks && m.blocks.length > 0 ? m.blocks : undefined,
  };
}

/** Upsert-by-id helper for both `message.new` (append or replace) and
 * `message.updated` (always a replace of the full row — contract §E.3). */
function upsertMessage(prev: Envelope<RawMessage> | undefined, msg: RawMessage): Envelope<RawMessage> | undefined {
  if (!prev) return prev;
  const idx = prev.items.findIndex((m) => m.id === msg.id);
  const items = idx >= 0 ? prev.items.map((m, i) => (i === idx ? msg : m)) : [...prev.items, msg];
  return { items, total: items.length };
}

interface LiveTurnState {
  textoParcial: string;
  status: "pensando" | "ociosa" | "erro" | null;
}

function emptyLive(): LiveTurnState {
  return { textoParcial: "", status: null };
}

// ─── Threads (conversation list) ────────────────────────────────────────────

/**
 * No dedicated "list" SSE feed exists (contract §E.3 scope is per
 * conversation) — `conversation.upsert` only arrives while THAT
 * conversation's stream is open (patched in `useJuliaMessagesAdapter`
 * below), so the list itself uses a short `staleTime` rather than
 * `Infinity`, and every mutation that changes it (create, send) also
 * invalidates it.
 */
export function useThreads() {
  const query = useQuery<Envelope<RawConversation>>({
    queryKey: CONVERSATIONS_KEY,
    queryFn: () => api.get<Envelope<RawConversation>>("/api/conversations"),
    staleTime: 15_000,
  });

  const sorted = useMemo(
    () =>
      (query.data?.items ?? [])
        .slice()
        .sort((a, b) => (b.last_message_at ?? b.created_at).localeCompare(a.last_message_at ?? a.created_at)),
    [query.data],
  );

  return {
    data: sorted.map(toChatThread),
    // ChatWindow's ChatAsyncResult scopes "loading" to `data.length === 0`
    // internally, so `isPending` (no data ever landed for this key) is the
    // correct signal, never a bare `isFetching`
    // (`KB § PATTERNS/frontend/lying-loading-state.md`).
    isLoading: query.isPending,
    isError: query.isError,
  };
}

export function useCreateConversation() {
  const qc = useQueryClient();
  return useMutation<RawConversation, unknown, { titulo?: string } | void>({
    mutationFn: (payload) => api.post<RawConversation>("/api/conversations", payload ?? {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY });
    },
  });
}

// ─── Messages + realtime (per opened conversation) ──────────────────────────

export function useJuliaMessagesAdapter(conversationId: string | null) {
  const qc = useQueryClient();
  const [live, setLive] = useState<LiveTurnState | null>(null);

  const query = useQuery<Envelope<RawMessage>>({
    queryKey: messagesKey(conversationId),
    queryFn: () => api.get<Envelope<RawMessage>>(`/api/conversations/${conversationId}/messages`),
    enabled: !!conversationId,
    staleTime: Infinity, // patched by the SSE stream below; reconciled once per turn (see session.status)
  });

  const onEvent = useCallback(
    (evt: RealtimeMessage) => {
      const p = evt.payload as Record<string, any>;

      switch (evt.event) {
        case "message.new": {
          const msg = p as unknown as RawMessage;
          qc.setQueryData<Envelope<RawMessage>>(messagesKey(conversationId), (prev) => upsertMessage(prev, msg));
          // A real assistant message landed — the streaming bubble's job is
          // done. (A `message.new` for the USER's own message, published
          // right before the turn starts, must not clear a bubble that
          // hasn't started yet — there is none at that point anyway.)
          if (msg.role === "assistant") setLive(null);
          break;
        }
        case "message.updated": {
          // Source of truth for `blocks` (contract §E.3, revised
          // 2026-09-14) — always a full-row replace, never merged.
          const msg = p as unknown as RawMessage;
          qc.setQueryData<Envelope<RawMessage>>(messagesKey(conversationId), (prev) => upsertMessage(prev, msg));
          break;
        }
        case "message.delta": {
          setLive((prev) => ({ ...(prev ?? emptyLive()), textoParcial: String(p.texto_parcial ?? "") }));
          break;
        }
        case "approval.requested":
        case "approval.resolved": {
          // No longer builds blocks (those come from `message.updated`) —
          // only keeps the approvals list in sync with any open surface.
          qc.invalidateQueries({ queryKey: APPROVALS_KEY_PREFIX });
          break;
        }
        case "session.status": {
          const status = p.status as LiveTurnState["status"];
          if (status === "pensando") {
            setLive((prev) => ({ ...(prev ?? emptyLive()), status }));
          } else {
            // Turn is over — the streaming bubble's job is done, and the
            // durable state lives in `blocks` on the real messages. Refetch
            // once to reconcile anything missed during a reconnect
            // (contract §E.3 "Frontend rendering rule").
            setLive(null);
            qc.invalidateQueries({ queryKey: messagesKey(conversationId) });
          }
          break;
        }
        case "conversation.upsert": {
          const conv = p as unknown as RawConversation;
          qc.setQueryData<Envelope<RawConversation>>(CONVERSATIONS_KEY, (prev) => {
            if (!prev) return prev;
            const idx = prev.items.findIndex((c) => c.id === conv.id);
            const items =
              idx >= 0
                ? prev.items.map((c, i) => (i === idx ? conv : c))
                : [...prev.items, conv];
            return { items, total: items.length };
          });
          break;
        }
        // `tool.started` / `tool.finished` no longer build UI state — the
        // persisted `blocks` (via `message.updated`) are the source of
        // truth. Falls through to default (no-op).
        default:
          break;
      }
    },
    [qc, conversationId],
  );

  useRealtimeStream(conversationId ? `/api/conversations/${conversationId}/stream` : null, {
    onEvent,
    getAuthToken,
    events: JULIA_STREAM_EVENTS,
  });

  const mapped = useMemo(() => (query.data?.items ?? []).map(toChatMessage), [query.data]);

  const liveBubble = useMemo<ChatMessage | null>(() => {
    if (!live) return null;
    const isThinking = live.status === "pensando";
    if (!live.textoParcial && !isThinking) return null;
    return {
      id: LIVE_ID,
      direction: "inbound",
      body: live.textoParcial || (isThinking ? "Julia está pensando…" : ""),
      created_at: new Date().toISOString(),
      pending: true,
    };
  }, [live]);

  return {
    data: liveBubble ? [...mapped, liveBubble] : mapped,
    isLoading: query.isPending,
    isError: query.isError,
  };
}

// ─── Send ────────────────────────────────────────────────────────────────

export function useJuliaSendAdapter(conversationId: string | null) {
  const qc = useQueryClient();

  const mutation = useMutation<
    { mensagem: RawMessage; status: string },
    unknown,
    { text: string }
  >({
    mutationFn: ({ text }) =>
      api.post<{ mensagem: RawMessage; status: string }>(
        `/api/conversations/${conversationId}/messages`,
        { texto: text },
      ),
    onSuccess: (resp) => {
      // Optimistic upsert — `message.new` over SSE will also deliver this
      // (idempotent upsert-by-id in `onEvent` above), covering the gap if
      // the stream connection is still establishing.
      qc.setQueryData<Envelope<RawMessage>>(messagesKey(conversationId), (prev) => upsertMessage(prev, resp.mensagem));
    },
  });

  return {
    mutateAsync: async ({ text }: { text: string }) => {
      try {
        return await mutation.mutateAsync({ text });
      } catch (err) {
        // ChatWindow surfaces this verbatim as the composer's inline error —
        // never faked as a success.
        throw new Error(errorMessage(err));
      }
    },
    isPending: mutation.isPending,
  };
}

// ─── Approval decision (ChatWindow seam, contract §E.7) ────────────────────

export function useJuliaApprovalActionAdapter() {
  const qc = useQueryClient();

  const mutation = useMutation<unknown, unknown, { approvalId: string; aprovada: boolean }>({
    mutationFn: ({ approvalId, aprovada }) =>
      api.post(`/api/approvals/${approvalId}/decision`, { aprovada }),
    onSettled: () => {
      // Covers both success (belt to the `approval.resolved` SSE patch) and
      // the "already_decided" / "orphaned" refetch contract §E.2 requires.
      qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY });
      qc.invalidateQueries({ queryKey: APPROVALS_KEY_PREFIX });
    },
  });

  return {
    decide: async (approvalId: string, aprovada: boolean) => {
      try {
        await mutation.mutateAsync({ approvalId, aprovada });
      } catch (err) {
        throw new Error(errorMessage(err));
      }
    },
    isPending: mutation.isPending,
  };
}

// ─── Adapter bag ────────────────────────────────────────────────────────────

export function buildJuliaChatAdapter(): ChatWindowAdapter {
  return {
    useThreads: () => useThreads(),
    useMessages: (_scopeId, threadId) => useJuliaMessagesAdapter(threadId),
    useSend: (_scopeId, threadId) => useJuliaSendAdapter(threadId),
    useApprovalAction: () => useJuliaApprovalActionAdapter(),
  };
}
