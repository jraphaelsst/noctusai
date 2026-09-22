/**
 * Studio agent chat adapter — Agent Studio CONTRACT.md §D6, §G "Conversar".
 *
 * Wires the seed `<ChatWindow>` organ (`@noctusai/lib/design-system`) onto
 * `/api/conversations` for a STUDIO agent (`agent_key` != "julia"),
 * mirroring `useJuliaChat.ts`'s shape (REST + one SSE stream per open
 * conversation patches the TanStack cache — no `refetchInterval`) with two
 * differences:
 *   - `agent_key` is a parameter (any studio agent, not just Julia) and
 *     conversation creation may pass an optional `client_id` (contract §D6).
 *   - No approval seam. §E.3 gives studio agents read-only
 *     `mcp__studio__*` tools with "no write tools" — there is no approval
 *     flow to wire, so `buildStudioChatAdapter` omits `useApprovalAction`
 *     entirely (the organ then renders any stray `approval` block
 *     read-only, same as an already-decided row).
 *   - Every assistant message with a `compiled_hash` gets one extra
 *     `{kind: "link"}` block reading "versão N · prompt sha256:abcd…",
 *     pointing at `/studio/prompts/:hash` (contract §G) — the version
 *     NUMBER is resolved separately (`useVersionNumber`, below) because
 *     `StudioMessage`/`StudioConversation` only carry the version's UUID,
 *     never its `versao` int; the hash itself already lives on the message.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { ApiError, errorMessage } from "@/lib/errors";
import { getAuthToken } from "@noctusai/seed/infra";
import { useRealtimeStream, type RealtimeMessage } from "@noctusai/lib";
import type {
  ChatBlock,
  ChatMessage,
  ChatThread,
  ChatWindowAdapter,
} from "@noctusai/lib/design-system";
import type { Envelope, StudioConversation, StudioMessage } from "@/api/studio/types-ke";

/** Every event name the studio conversation stream emits — mirrors
 * `JULIA_STREAM_EVENTS` minus `approval.*` (no write tools, §E.3). The
 * `events` list MUST name every one, or the seed transport silently drops
 * it (`seed/lib/frontend/src/realtime.ts`). */
export const STUDIO_STREAM_EVENTS = [
  "message.new",
  "message.updated",
  "message.delta",
  "tool.started",
  "tool.finished",
  "session.status",
  "conversation.upsert",
] as const;

const threadsKey = (agentKey: string) => ["studio", agentKey, "conversations"] as const;
const messagesKey = (agentKey: string, conversationId: string | null) =>
  [...threadsKey(agentKey), conversationId, "messages"] as const;
const versionNumberKey = (agentKey: string, versionId: string) =>
  ["studio", agentKey, "versions", versionId, "versao"] as const;

const LIVE_ID = "__live__";

// ─── Mapping helpers ────────────────────────────────────────────────────────

function toChatThread(c: StudioConversation): ChatThread {
  return {
    id: c.id,
    title: c.titulo || "Nova conversa",
    lastMessageAt: c.last_message_at,
  };
}

/** Truncated display form of a `"sha256:<hex>"` compiled hash — "sha256:1a2b3c4d…". */
function shortHash(hash: string): string {
  const prefixLen = "sha256:".length + 8;
  return hash.length > prefixLen ? `${hash.slice(0, prefixLen)}…` : hash;
}

function toChatMessage(m: StudioMessage, versao: number | null): ChatMessage {
  const blocks: ChatBlock[] = Array.isArray(m.blocks) ? [...(m.blocks as ChatBlock[])] : [];
  if (m.role === "assistant" && m.compiled_hash) {
    const label = versao != null ? `versão ${versao} · prompt ${shortHash(m.compiled_hash)}` : `prompt ${shortHash(m.compiled_hash)}`;
    // `compiled_hash` is server data, not user input, but it still lands in a URL
    // path segment — encode it so a stray "/", "?", or "#" in the hash can never
    // reroute the link off `/studio/prompts/:hash` (path traversal / open redirect).
    blocks.push({ kind: "link", label, href: `/studio/prompts/${encodeURIComponent(m.compiled_hash)}` });
  }
  return {
    id: m.id,
    direction: m.role === "user" ? "outbound" : "inbound",
    body: m.texto,
    created_at: m.created_at,
    blocks: blocks.length > 0 ? blocks : undefined,
  };
}

function upsertMessage(
  prev: Envelope<StudioMessage> | undefined,
  msg: StudioMessage,
): Envelope<StudioMessage> | undefined {
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

// ─── Version number lookup (display-only) ──────────────────────────────────

interface VersionSummaryLite {
  versao: number;
}

/** Resolves a version's `versao` int off its UUID (contract §D1
 * `GET .../versions/{vid}`). A published version is immutable, so this is
 * cached forever once fetched. */
function useVersionNumber(agentKey: string, versionId: string | null): number | null {
  const query = useQuery<VersionSummaryLite>({
    queryKey: versionNumberKey(agentKey, versionId ?? ""),
    queryFn: () => api.get<VersionSummaryLite>(`/api/studio/agents/${agentKey}/versions/${versionId}`),
    enabled: !!agentKey && !!versionId,
    staleTime: Infinity,
  });
  return query.data?.versao ?? null;
}

/** Reactive read of one conversation off the shared threads cache (no
 * dedicated "get conversation by id" endpoint exists) — `select` keeps this
 * subscribed to `conversation.upsert` patches landing on the list query. */
function useConversationFromCache(agentKey: string, conversationId: string | null): StudioConversation | null {
  const query = useQuery<Envelope<StudioConversation>, unknown, StudioConversation | null>({
    queryKey: threadsKey(agentKey),
    queryFn: () => api.get<Envelope<StudioConversation>>("/api/conversations", { agent_key: agentKey }),
    enabled: !!agentKey && !!conversationId,
    staleTime: 15_000,
    select: (data) => data.items.find((c) => c.id === conversationId) ?? null,
  });
  return query.data ?? null;
}

// ─── Threads (conversation list) ────────────────────────────────────────────

export function useStudioThreads(agentKey: string) {
  const query = useQuery<Envelope<StudioConversation>>({
    queryKey: threadsKey(agentKey),
    queryFn: () => api.get<Envelope<StudioConversation>>("/api/conversations", { agent_key: agentKey }),
    enabled: !!agentKey,
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
    // ChatWindow scopes "loading" to `data.length === 0` internally, so
    // `isPending` (no data ever landed) is the correct signal here, never a
    // bare `isFetching` (`KB § PATTERNS/frontend/lying-loading-state.md`).
    isLoading: query.isPending,
    isError: query.isError,
  };
}

export function useCreateStudioConversation(agentKey: string) {
  const qc = useQueryClient();
  return useMutation<StudioConversation, unknown, { clientId?: string } | undefined>({
    mutationFn: (payload) =>
      api.post<StudioConversation>("/api/conversations", {
        agent_key: agentKey,
        client_id: payload?.clientId ?? undefined,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: threadsKey(agentKey) }),
  });
}

// ─── Messages + realtime (per opened conversation) ──────────────────────────

export function useStudioMessagesAdapter(agentKey: string, conversationId: string | null) {
  const qc = useQueryClient();
  const [live, setLive] = useState<LiveTurnState | null>(null);

  const query = useQuery<Envelope<StudioMessage>>({
    queryKey: messagesKey(agentKey, conversationId),
    queryFn: () => api.get<Envelope<StudioMessage>>(`/api/conversations/${conversationId}/messages`),
    enabled: !!conversationId,
    staleTime: Infinity, // patched by the SSE stream below; reconciled once per turn (session.status)
  });

  const conversation = useConversationFromCache(agentKey, conversationId);
  const versao = useVersionNumber(agentKey, conversation?.version_id ?? null);

  const onEvent = useCallback(
    (evt: RealtimeMessage) => {
      const p = evt.payload as Record<string, any>;

      switch (evt.event) {
        case "message.new": {
          const msg = p as unknown as StudioMessage;
          qc.setQueryData<Envelope<StudioMessage>>(messagesKey(agentKey, conversationId), (prev) => upsertMessage(prev, msg));
          if (msg.role === "assistant") setLive(null);
          break;
        }
        case "message.updated": {
          const msg = p as unknown as StudioMessage;
          qc.setQueryData<Envelope<StudioMessage>>(messagesKey(agentKey, conversationId), (prev) => upsertMessage(prev, msg));
          break;
        }
        case "message.delta": {
          setLive((prev) => ({ ...(prev ?? emptyLive()), textoParcial: String(p.texto_parcial ?? "") }));
          break;
        }
        case "session.status": {
          const status = p.status as LiveTurnState["status"];
          if (status === "pensando") {
            setLive((prev) => ({ ...(prev ?? emptyLive()), status }));
          } else {
            setLive(null);
            qc.invalidateQueries({ queryKey: messagesKey(agentKey, conversationId) });
          }
          break;
        }
        case "conversation.upsert": {
          const conv = p as unknown as StudioConversation;
          qc.setQueryData<Envelope<StudioConversation>>(threadsKey(agentKey), (prev) => {
            if (!prev) return prev;
            const idx = prev.items.findIndex((c) => c.id === conv.id);
            const items = idx >= 0 ? prev.items.map((c, i) => (i === idx ? conv : c)) : [...prev.items, conv];
            return { items, total: items.length };
          });
          break;
        }
        // `tool.started`/`tool.finished` no longer build UI state — the
        // persisted `blocks` (via `message.updated`) are the source of
        // truth (mirrors `useJuliaChat.ts`).
        default:
          break;
      }
    },
    [qc, agentKey, conversationId],
  );

  useRealtimeStream(conversationId ? `/api/conversations/${conversationId}/stream` : null, {
    onEvent,
    getAuthToken,
    events: STUDIO_STREAM_EVENTS,
  });

  const mapped = useMemo(() => (query.data?.items ?? []).map((m) => toChatMessage(m, versao)), [query.data, versao]);

  const liveBubble = useMemo<ChatMessage | null>(() => {
    if (!live) return null;
    const isThinking = live.status === "pensando";
    if (!live.textoParcial && !isThinking) return null;
    return {
      id: LIVE_ID,
      direction: "inbound",
      body: live.textoParcial || (isThinking ? "Pensando…" : ""),
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

export function useStudioSendAdapter(agentKey: string, conversationId: string | null) {
  const qc = useQueryClient();
  // Reactive cooldown countdown — ticked here, not in the organ, mirroring
  // `useJuliaSendAdapter` (`ChatSendResult.retryAfterSeconds` is purely
  // reactive; `ChatWindow` never runs its own timer).
  const [retryAfterSeconds, setRetryAfterSeconds] = useState<number | null>(null);

  useEffect(() => {
    if (retryAfterSeconds === null) return;
    if (retryAfterSeconds <= 0) {
      setRetryAfterSeconds(null);
      return;
    }
    const id = setTimeout(() => {
      setRetryAfterSeconds((prev) => (prev === null ? null : prev - 1));
    }, 1000);
    return () => clearTimeout(id);
  }, [retryAfterSeconds]);

  const mutation = useMutation<{ mensagem: StudioMessage; status: string }, unknown, { text: string }>({
    mutationFn: ({ text }) =>
      api.post<{ mensagem: StudioMessage; status: string }>(`/api/conversations/${conversationId}/messages`, {
        texto: text,
      }),
    onSuccess: (resp) => {
      qc.setQueryData<Envelope<StudioMessage>>(messagesKey(agentKey, conversationId), (prev) => upsertMessage(prev, resp.mensagem));
    },
  });

  return {
    mutateAsync: async ({ text }: { text: string }) => {
      try {
        return await mutation.mutateAsync({ text });
      } catch (err) {
        if (
          err instanceof ApiError &&
          err.status === 429 &&
          typeof err.retryAfterSeconds === "number" &&
          err.retryAfterSeconds > 0
        ) {
          setRetryAfterSeconds(err.retryAfterSeconds);
        }
        throw new Error(errorMessage(err));
      }
    },
    isPending: mutation.isPending,
    retryAfterSeconds,
  };
}

// ─── Adapter bag ────────────────────────────────────────────────────────────

/** Builds a `ChatWindowAdapter` scoped to one studio agent (contract §G
 * "Conversar"). `useApprovalAction` is deliberately omitted (see file
 * header). */
export function buildStudioChatAdapter(agentKey: string): ChatWindowAdapter {
  return {
    useThreads: () => useStudioThreads(agentKey),
    useMessages: (_scopeId, threadId) => useStudioMessagesAdapter(agentKey, threadId),
    useSend: (_scopeId, threadId) => useStudioSendAdapter(agentKey, threadId),
  };
}
