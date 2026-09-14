/**
 * Julia chat adapter — contract §E.2 (conversations/messages), §E.3 (SSE),
 * §E.7 (ChatWindow seams).
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
 * ── Live-turn scaffold (contract ambiguity, flagged in the delivery report)
 * `tool.started` / `tool.finished` / `approval.requested` / `approval.resolved`
 * / `message.delta` carry NO conversation-message id — only `message.new`
 * does, and the backend resets its own `current_blocks` accumulator to `[]`
 * on every `message.new` (`app/routers/conversations_router.py
 * ::_run_turn_background`), so a client cannot reliably attribute a given
 * tool/approval event to a specific PERSISTED message purely from the SSE
 * stream. This adapter therefore renders one synthetic "live turn" bubble
 * per open conversation (`id: "__live__"`) that accumulates
 * `message.delta` text + `tool.*`/`approval.*` blocks while
 * `session.status === "pensando"`, and is cleared the moment `message.new`
 * lands OR `session.status` moves away from `pensando` — never left
 * stranded showing stale activity from a finished turn. The DB-persisted
 * `blocks` on each real message (visible after the next `GET
 * .../messages`, e.g. on reopen) are the durable source of truth.
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
 * drops it (`seed/lib/frontend/src/realtime.ts` — "load-bearing"). */
export const JULIA_STREAM_EVENTS = [
  "message.new",
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

interface LiveTurnState {
  textoParcial: string;
  blocks: ChatBlock[];
  status: "pensando" | "ociosa" | "erro" | null;
}

function emptyLive(): LiveTurnState {
  return { textoParcial: "", blocks: [], status: null };
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
    staleTime: Infinity, // patched exclusively by the SSE stream below
  });

  const onEvent = useCallback(
    (evt: RealtimeMessage) => {
      const p = evt.payload as Record<string, any>;

      switch (evt.event) {
        case "message.new": {
          const msg = p as unknown as RawMessage;
          qc.setQueryData<Envelope<RawMessage>>(messagesKey(conversationId), (prev) => {
            if (!prev) return prev;
            const idx = prev.items.findIndex((m) => m.id === msg.id);
            const items =
              idx >= 0
                ? prev.items.map((m, i) => (i === idx ? msg : m))
                : [...prev.items, msg];
            return { items, total: items.length };
          });
          // A real message landed — the live scaffold's job is done.
          setLive(null);
          break;
        }
        case "message.delta": {
          setLive((prev) => ({ ...(prev ?? emptyLive()), textoParcial: String(p.texto_parcial ?? "") }));
          break;
        }
        case "tool.started": {
          const block: ChatBlock = {
            kind: "tool",
            toolUseId: String(p.tool_use_id),
            name: String(p.tool_name ?? ""),
            status: "running",
            resumo: p.resumo ?? undefined,
          };
          setLive((prev) => ({ ...(prev ?? emptyLive()), blocks: [...(prev?.blocks ?? []), block] }));
          break;
        }
        case "tool.finished": {
          const resultado = (p.resultado ?? "ok") as "ok" | "erro" | "negada";
          setLive((prev) => {
            const base = prev ?? emptyLive();
            const idx = base.blocks.findIndex(
              (b) => b.kind === "tool" && b.toolUseId === String(p.tool_use_id),
            );
            if (idx < 0) {
              const block: ChatBlock = {
                kind: "tool",
                toolUseId: String(p.tool_use_id),
                name: String(p.tool_name ?? ""),
                status: resultado,
              };
              return { ...base, blocks: [...base.blocks, block] };
            }
            const blocks = base.blocks.map((b, i) =>
              i === idx && b.kind === "tool" ? { ...b, status: resultado } : b,
            );
            return { ...base, blocks };
          });
          break;
        }
        case "approval.requested": {
          const block: ChatBlock = {
            kind: "approval",
            approvalId: String(p.id),
            resumo: String(p.resumo ?? ""),
            diff: p.diff ?? undefined,
            decision: "pendente",
          };
          setLive((prev) => ({ ...(prev ?? emptyLive()), blocks: [...(prev?.blocks ?? []), block] }));
          break;
        }
        case "approval.resolved": {
          const decision = (p.decision ?? "pendente") as
            | "pendente"
            | "aprovada"
            | "negada"
            | "expirada";
          setLive((prev) => {
            if (!prev) return prev;
            const idx = prev.blocks.findIndex(
              (b) => b.kind === "approval" && b.approvalId === String(p.approval_id),
            );
            if (idx < 0) return prev;
            const blocks = prev.blocks.map((b, i) =>
              i === idx && b.kind === "approval" ? { ...b, decision } : b,
            );
            return { ...prev, blocks };
          });
          break;
        }
        case "session.status": {
          const status = p.status as LiveTurnState["status"];
          if (status === "pensando") {
            setLive((prev) => ({ ...(prev ?? emptyLive()), status }));
          } else {
            // Turn is over — nothing accumulated here is durable; the
            // persisted `blocks` on the real message (next GET) are.
            setLive(null);
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
    const hasBlocks = live.blocks.length > 0;
    const isThinking = live.status === "pensando";
    if (!hasBlocks && !live.textoParcial && !isThinking) return null;
    return {
      id: LIVE_ID,
      direction: "inbound",
      body: live.textoParcial || (isThinking ? "Julia está pensando…" : ""),
      created_at: new Date().toISOString(),
      pending: true,
      blocks: hasBlocks ? live.blocks : undefined,
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
      qc.setQueryData<Envelope<RawMessage>>(messagesKey(conversationId), (prev) => {
        if (!prev) return prev;
        const idx = prev.items.findIndex((m) => m.id === resp.mensagem.id);
        const items =
          idx >= 0
            ? prev.items.map((m, i) => (i === idx ? resp.mensagem : m))
            : [...prev.items, resp.mensagem];
        return { items, total: items.length };
      });
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
      qc.invalidateQueries({ queryKey: ["agents", "approvals"] });
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
