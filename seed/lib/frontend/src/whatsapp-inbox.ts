/**
 * WhatsApp inbox hooks - conversation list, message thread, send, read-state
 * and the realtime feed, for the backend router
 * `noctusai_seed.whatsapp_inbox_router.create_whatsapp_inbox_router`.
 *
 * Same injection idiom as `createWhatsAppConnectionsHooks`: the product hands
 * its authenticated `ApiClient` to `createWhatsAppInboxHooks(api, options)`
 * ONCE and gets the hook bag back (`<WhatsAppInbox hooks={...}/>` takes it as a prop).
 *
 * Server-state rules (KB § PATTERNS/common/server-state-family-index.md):
 *  - never a bare `isLoading`: `showSkeleton` (first load only) vs
 *    `isRefreshing` (quiet refetch over data already on screen);
 *  - every write goes through `useCacheWriteMutation` and PUTS the server's
 *    answer into the lists it touches (message thread + chat preview) - it
 *    never just invalidates;
 *  - realtime events PATCH the same caches (`setQueriesData`), idempotently
 *    (a resumed stream may redeliver) - they never trigger a refetch;
 *  - when the stream is not open (no token provider, or reconnecting) the
 *    organ polls instead (`pollMs`), so the inbox is never silently frozen.
 *
 * Wire contract (backend DTOs; renaming a field is a bump on both sides):
 *   GET  {base}/{conn}/chats?q&limit&cursor          -> { items: InboxChat[], next_cursor }  newest activity first
 *   GET  {base}/{conn}/chats/{chat}/messages?before&limit -> { items: InboxMessage[], has_more }
 *        items are chronological INSIDE a page; `before` = "<iso>|<id>" of the oldest message held
 *   POST {base}/{conn}/chats/{chat}/messages { text } -> InboxMessage
 *   POST {base}/{conn}/chats/{chat}/read              -> 204
 *   POST {base}/{conn}/backfill                       -> 202 { status }
 *   GET  {base}/{conn}/events                         (SSE: message.new / chat.upsert / message.ack / chat.read / session.status)
 * chat ids are WhatsApp JIDs ("5511999998888@c.us") and are URL-encoded in paths.
 */
import { useCallback, useMemo } from 'react';
import {
  useInfiniteQuery,
  useQueryClient,
  type InfiniteData,
  type QueryKey,
} from '@tanstack/react-query';
import type { ApiClient } from './api';
import { useCacheWriteMutation } from './cache-writes';
import { useRealtimeStream, type RealtimeMessage, type RealtimeStatus } from './realtime';

// ---------------------------------------------------------------------------
// Types - mirror noctusai_lib.integrations.whatsapp.inbox.types
// ---------------------------------------------------------------------------

export interface InboxChat {
  chat_id: string;
  name: string;
  /** E.164 ("+5511999998888") or null (group / unresolved @lid). */
  phone: string | null;
  is_group: boolean;
  last_message_preview: string;
  last_message_at: string | null;
  last_message_from_me: boolean | null;
  unread_count: number;
}

export interface InboxMessage {
  /** The WAHA message id (stable: dedup key, ack key). Optimistic stand-ins carry `optimistic:*`. */
  id: string;
  chat_id: string;
  from_me: boolean;
  body: string;
  type: string;
  media_url: string | null;
  /** WAHA ack: -1 error · 0 pending · 1 server · 2 device · 3 read · 4 played. */
  ack: number | null;
  timestamp: string;
  sender_name: string | null;
}

export interface InboxChatsPage {
  items: InboxChat[];
  next_cursor: string | null;
}

export interface InboxMessagesPage {
  items: InboxMessage[];
  has_more: boolean;
}

export type InboxChatsData = InfiniteData<InboxChatsPage, string | null>;
export type InboxMessagesData = InfiniteData<InboxMessagesPage, string | null>;

export interface CreateWhatsAppInboxHooksOptions {
  /** Default `/api/whatsapp/connections`. */
  basePath?: string;
  /**
   * Fresh bearer token for the SSE stream (`EventSource` cannot send headers, so the stream is
   * `fetch`-based and REQUIRES a token provider). Omit => no stream, the inbox polls instead.
   */
  getAuthToken?: () => Promise<string | null>;
  /** Prefix for the absolute stream URL when the API is not same-origin. Default ''. */
  getBaseUrl?: () => string;
}

// ---------------------------------------------------------------------------
// Pure cache ops (exported for tests) - tolerate an uncached list (undefined in -> undefined out)
// ---------------------------------------------------------------------------

export const inboxCacheOps = {
  /** Replace a chat in place wherever it is cached; no-op when absent. */
  patchChat(old: InboxChatsData | undefined, chatId: string, patch: Partial<InboxChat>): InboxChatsData | undefined {
    if (!old) return old;
    let touched = false;
    const pages = old.pages.map((page) => {
      if (!page.items.some((c) => c.chat_id === chatId)) return page;
      touched = true;
      return { ...page, items: page.items.map((c) => (c.chat_id === chatId ? { ...c, ...patch } : c)) };
    });
    return touched ? { ...old, pages } : old;
  },

  /** New activity on a chat: merge into (or insert) the chat and move it to the top of the newest page. */
  bumpChat(old: InboxChatsData | undefined, chat: InboxChat): InboxChatsData | undefined {
    if (!old || old.pages.length === 0) return old;
    let merged: InboxChat = chat;
    const pages = old.pages.map((page) => {
      const hit = page.items.find((c) => c.chat_id === chat.chat_id);
      if (!hit) return page;
      merged = { ...hit, ...chat };
      return { ...page, items: page.items.filter((c) => c.chat_id !== chat.chat_id) };
    });
    const [first, ...rest] = pages;
    return { ...old, pages: [{ ...first, items: [merged, ...first.items] }, ...rest] };
  },

  /** Patch a CACHED chat and move it to the top (a send: same chat, new activity). No-op when not cached. */
  bumpChatWith(old: InboxChatsData | undefined, chatId: string, patch: Partial<InboxChat>): InboxChatsData | undefined {
    const hit = old?.pages.flatMap((p) => p.items).find((c) => c.chat_id === chatId);
    return hit ? inboxCacheOps.bumpChat(old, { ...hit, ...patch }) : old;
  },

  /** Idempotent append to the NEWEST page (pages[0]); a message already cached (by id) is left alone. */
  appendMessage(old: InboxMessagesData | undefined, message: InboxMessage): InboxMessagesData | undefined {
    if (!old || old.pages.length === 0) return old;
    if (old.pages.some((p) => p.items.some((m) => m.id === message.id))) return old;
    const [newest, ...rest] = old.pages;
    return { ...old, pages: [{ ...newest, items: [...newest.items, message] }, ...rest] };
  },

  patchMessage(old: InboxMessagesData | undefined, id: string, patch: Partial<InboxMessage>): InboxMessagesData | undefined {
    if (!old) return old;
    let touched = false;
    const pages = old.pages.map((page) => {
      if (!page.items.some((m) => m.id === id)) return page;
      touched = true;
      return { ...page, items: page.items.map((m) => (m.id === id ? { ...m, ...patch } : m)) };
    });
    return touched ? { ...old, pages } : old;
  },

  /**
   * The server answered a send: swap the optimistic stand-in for the real message. If the realtime
   * stream already delivered the real one, just drop the stand-in (never two copies).
   */
  settleSent(old: InboxMessagesData | undefined, tempId: string, saved: InboxMessage): InboxMessagesData | undefined {
    if (!old) return old;
    const alreadyThere = old.pages.some((p) => p.items.some((m) => m.id === saved.id));
    const pages = old.pages.map((page) => ({
      ...page,
      items: alreadyThere
        ? page.items.filter((m) => m.id !== tempId)
        : page.items.map((m) => (m.id === tempId ? saved : m)),
    }));
    return { ...old, pages };
  },
};

/** pages[0] is the newest; each page is chronological -> oldest-first overall. */
export function flattenMessages(data: InboxMessagesData | undefined): InboxMessage[] {
  return (data?.pages ?? []).slice().reverse().flatMap((p) => p.items);
}

export function flattenChats(data: InboxChatsData | undefined): InboxChat[] {
  return (data?.pages ?? []).flatMap((p) => p.items);
}

/** `<iso>|<id>` of the oldest message held - the `before` cursor of the next older page. */
export function olderCursor(page: InboxMessagesPage): string | undefined {
  const oldest = page.items[0];
  return page.has_more && oldest ? `${oldest.timestamp}|${oldest.id}` : undefined;
}

function previewOf(body: string): string {
  const text = body.trim();
  return text.length > 140 ? `${text.slice(0, 139).trimEnd()}…` : text;
}

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

export function createWhatsAppInboxHooks(api: ApiClient, options: CreateWhatsAppInboxHooksOptions = {}) {
  const basePath = options.basePath ?? '/api/whatsapp/connections';
  const ROOT = ['whatsapp-inbox', basePath] as const;
  const chatsPrefix = (cid: string | null) => [...ROOT, cid, 'chats'] as const;
  const chatsKey = (cid: string | null, q: string) => [...chatsPrefix(cid), q] as const;
  const messagesKey = (cid: string | null, chatId: string | null) => [...ROOT, cid, 'messages', chatId] as const;
  /** The unfiltered list - the only one a live bump may INSERT into (a search list would gain non-matches). */
  const isUnfiltered = (key: QueryKey) => key[4] === '';
  const chatPath = (cid: string, chatId: string) => `${basePath}/${encodeURIComponent(cid)}/chats/${encodeURIComponent(chatId)}`;

  /** Chat list (infinite, newest activity first). `q` filters server-side. */
  function useInboxChats(
    connectionId: string | null,
    opts: { q?: string; pageSize?: number; pollMs?: number | false; enabled?: boolean } = {},
  ) {
    const q = (opts.q ?? '').trim();
    const pageSize = opts.pageSize ?? 30;
    const query = useInfiniteQuery<InboxChatsPage, Error, InboxChatsData, QueryKey, string | null>({
      queryKey: chatsKey(connectionId, q),
      initialPageParam: null,
      queryFn: ({ pageParam }) => {
        const params: Record<string, any> = { limit: pageSize };
        if (q) params.q = q;
        if (pageParam) params.cursor = pageParam;
        return api.get<InboxChatsPage>(`${basePath}/${encodeURIComponent(connectionId ?? '')}/chats`, params);
      },
      getNextPageParam: (last) => last.next_cursor ?? undefined,
      enabled: !!connectionId && (opts.enabled ?? true),
      refetchInterval: opts.pollMs || false,
    });
    const chats = useMemo(() => flattenChats(query.data), [query.data]);
    return {
      ...query,
      chats,
      /** First load only - a refetch over data already on screen never shows a skeleton. */
      showSkeleton: query.isPending && !query.data,
      /** Quiet background refresh. */
      isRefreshing: query.isFetching && !!query.data,
    };
  }

  /** Message thread, oldest -> newest, paging backwards through history. */
  function useInboxMessages(
    connectionId: string | null,
    chatId: string | null,
    opts: { pageSize?: number; pollMs?: number | false } = {},
  ) {
    const pageSize = opts.pageSize ?? 50;
    const query = useInfiniteQuery<InboxMessagesPage, Error, InboxMessagesData, QueryKey, string | null>({
      queryKey: messagesKey(connectionId, chatId),
      initialPageParam: null,
      queryFn: ({ pageParam }) => {
        const params: Record<string, any> = { limit: pageSize };
        if (pageParam) params.before = pageParam;
        return api.get<InboxMessagesPage>(`${chatPath(connectionId ?? '', chatId ?? '')}/messages`, params);
      },
      getNextPageParam: olderCursor,
      enabled: !!connectionId && !!chatId,
      refetchInterval: opts.pollMs || false,
    });
    const messages = useMemo(() => flattenMessages(query.data), [query.data]);
    return {
      ...query,
      messages,
      showSkeleton: query.isPending && !query.data,
      isRefreshing: query.isFetching && !!query.data,
    };
  }

  /**
   * Send text to the open chat. The message is drawn at once (optimistic stand-in), then replaced by
   * the server's message; the chat list preview + order follow. A failure rolls both back and the
   * thrown Error carries the server's user-facing message (ChatWindow shows it verbatim).
   */
  function useSendInboxMessage(connectionId: string | null, chatId: string | null) {
    return useCacheWriteMutation<InboxMessage, string>({
      mutationFn: (text) => api.post<InboxMessage>(`${chatPath(connectionId ?? '', chatId ?? '')}/messages`, { text }),
      targets: (text) => [
        {
          queryKey: messagesKey(connectionId, chatId),
          optimistic: (old: InboxMessagesData | undefined, _vars, ctx) =>
            inboxCacheOps.appendMessage(old, {
              id: ctx.tempId,
              chat_id: chatId ?? '',
              from_me: true,
              body: text,
              type: 'chat',
              media_url: null,
              ack: 0,
              timestamp: new Date().toISOString(),
              sender_name: null,
            }),
          commit: (old: InboxMessagesData | undefined, saved, _vars, ctx) => inboxCacheOps.settleSent(old, ctx.tempId, saved),
        },
        {
          queryKey: chatsPrefix(connectionId),
          match: 'prefix',
          predicate: isUnfiltered,
          optimistic: (old: InboxChatsData | undefined) =>
            chatId
              ? inboxCacheOps.bumpChatWith(old, chatId, {
                  last_message_preview: previewOf(text),
                  last_message_at: new Date().toISOString(),
                  last_message_from_me: true,
                })
              : old,
          commit: (old: InboxChatsData | undefined, saved) =>
            chatId
              ? inboxCacheOps.bumpChatWith(old, chatId, {
                  last_message_preview: previewOf(saved.body),
                  last_message_at: saved.timestamp,
                  last_message_from_me: true,
                })
              : old,
        },
      ],
    });
  }

  /** Mark a chat read (badge cleared at once; the server confirms with `chat.read`). */
  function useMarkChatRead(connectionId: string | null) {
    return useCacheWriteMutation<unknown, string>({
      mutationFn: (chatId) => api.post(`${chatPath(connectionId ?? '', chatId)}/read`),
      targets: (chatId) => [
        {
          queryKey: chatsPrefix(connectionId),
          match: 'prefix',
          optimistic: (old: InboxChatsData | undefined) => inboxCacheOps.patchChat(old, chatId, { unread_count: 0 }),
        },
      ],
    });
  }

  /** Kick a history backfill from the WAHA NOWEB store (202; runs server-side). */
  function useBackfillInbox(connectionId: string | null) {
    return useCacheWriteMutation<{ status: string }, void>({
      mutationFn: () => api.post<{ status: string }>(`${basePath}/${encodeURIComponent(connectionId ?? '')}/backfill`),
      // The result is a job ticket, not rows: the imported chats arrive via the stream / this refetch.
      targets: [{ queryKey: chatsPrefix(connectionId) }],
    });
  }

  /**
   * Subscribe the connection's event stream and patch the caches in place. Mount ONCE per
   * connection (the organ does). Returns the stream status so the caller can fall back to polling
   * while it is not `open`. Without `options.getAuthToken` there is no stream: status stays
   * `closed` and the organ polls.
   */
  function useInboxEvents(connectionId: string | null, opts: { enabled?: boolean } = {}): { status: RealtimeStatus } {
    const qc = useQueryClient();
    const onEvent = useCallback(
      (evt: RealtimeMessage) => {
        const p = evt.payload as Record<string, any>;
        switch (evt.event) {
          case 'message.new': {
            const message = p.message as InboxMessage | undefined;
            if (!message || !p.chat_id) return;
            qc.setQueryData<InboxMessagesData>(messagesKey(connectionId, p.chat_id), (old) => inboxCacheOps.appendMessage(old, message));
            break;
          }
          case 'chat.upsert': {
            const chat = p.chat as InboxChat | undefined;
            if (!chat) return;
            qc.setQueriesData<InboxChatsData>(
              { queryKey: chatsPrefix(connectionId), predicate: (q) => isUnfiltered(q.queryKey) },
              (old) => inboxCacheOps.bumpChat(old, chat),
            );
            qc.setQueriesData<InboxChatsData>(
              { queryKey: chatsPrefix(connectionId), predicate: (q) => !isUnfiltered(q.queryKey) },
              (old) => inboxCacheOps.patchChat(old, chat.chat_id, chat),
            );
            break;
          }
          case 'message.ack': {
            if (!p.chat_id || !p.id) return;
            qc.setQueryData<InboxMessagesData>(messagesKey(connectionId, p.chat_id), (old) =>
              inboxCacheOps.patchMessage(old, p.id, { ack: p.ack }),
            );
            break;
          }
          case 'chat.read': {
            if (!p.chat_id) return;
            qc.setQueriesData<InboxChatsData>({ queryKey: chatsPrefix(connectionId) }, (old) =>
              inboxCacheOps.patchChat(old, p.chat_id, { unread_count: p.unread_count ?? 0 }),
            );
            break;
          }
          default:
            break; // session.status etc.: the connections hooks own the status cache
        }
      },
      [qc, connectionId],
    );
    const url = connectionId && options.getAuthToken
      ? `${options.getBaseUrl?.() ?? ''}${basePath}/${encodeURIComponent(connectionId)}/events`
      : null;
    const stream = useRealtimeStream(url, {
      onEvent,
      // Required by the transport: a stream without a token 401s forever, silently.
      getAuthToken: options.getAuthToken ?? (async () => null),
      enabled: (opts.enabled ?? true) && !!options.getAuthToken,
      events: ['message.new', 'chat.upsert', 'message.ack', 'chat.read', 'session.status'],
    });
    return { status: stream.status };
  }

  return {
    useInboxChats,
    useInboxMessages,
    useSendInboxMessage,
    useMarkChatRead,
    useBackfillInbox,
    useInboxEvents,
  };
}

export type WhatsAppInboxHooks = ReturnType<typeof createWhatsAppInboxHooks>;
