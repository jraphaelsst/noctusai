/**
 * WhatsAppInbox - the WhatsApp "Conversas" screen: searchable chat list (unread
 * badge) + message thread + composer, on the seed `ChatWindow` organ.
 *
 * It is the adapter between the inbox hooks (`createWhatsAppInboxHooks`) and
 * `ChatWindow`'s provider-blind adapter bag - the product writes no glue:
 *
 *   const hooks = createWhatsAppInboxHooks(api, { getAuthToken });   // once, module scope
 *   <WhatsAppInbox hooks={hooks} connectionId={id}
 *                  initialChatId={searchParams.get('chat')}
 *                  renderChatHeaderExtra={(chat) => <VerLeadLink chatId={chat.chat_id} />} />
 *
 * - `initialChatId` deep-links a conversation (e.g. from a lead). If that chat is
 *   not in the loaded pages it is looked up by a server search on its id and
 *   merged into the list, so the link never opens a blank pane.
 * - `renderChatHeaderExtra(chat)` renders in the open thread's header (the product
 *   puts "ver lead" there).
 * - Realtime: one SSE stream per connection patches the caches; while it is not
 *   open the organ polls (`pollMs`), so a frozen inbox is never silent.
 * - Loading follows the server-state rules: skeleton on the FIRST load only; a
 *   refetch over data already shown never blanks the list.
 */
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Search } from 'lucide-react';

import { ChatWindow } from '../../design-system/chat';
import type { ChatMessage, ChatThread, ChatWindowAdapter } from '../../design-system/chat';
import { Button } from '../../design-system/ui/Button';
import { Input } from '../../design-system/ui/Input';
import type { InboxChat, InboxMessage, WhatsAppInboxHooks } from '../../whatsapp-inbox';

export interface WhatsAppInboxProps {
  hooks: WhatsAppInboxHooks;
  connectionId: string | null;
  /** Chat (WhatsApp JID) to open once it is known - deep link from a lead. */
  initialChatId?: string | null;
  /** Rendered in the open thread's header, between the title and the controls. */
  renderChatHeaderExtra?: (chat: InboxChat) => ReactNode;
  /** Called on every selection change (user click, back, or the deep link applying). */
  onSelectChat?: (chatId: string | null) => void;
  /** Poll interval while the realtime stream is not open. Default 10s; `0` disables polling. */
  fallbackPollMs?: number;
  searchPlaceholder?: string;
  emptyThreadsLabel?: string;
  className?: string;
}

const SEARCH_DEBOUNCE_MS = 300;

function directionOf(fromMe: boolean | null): ChatThread['lastDirection'] {
  return fromMe === null ? null : fromMe ? 'outbound' : 'inbound';
}

export function toThread(chat: InboxChat): ChatThread {
  return {
    id: chat.chat_id,
    title: chat.name,
    lastMessagePreview: chat.last_message_preview,
    lastMessageAt: chat.last_message_at,
    lastDirection: directionOf(chat.last_message_from_me),
    unreadCount: chat.unread_count,
    meta: { chat },
  };
}

/** Media without a caption must still read as something in the thread. */
function bodyOf(message: InboxMessage): string {
  if (message.body.trim()) return message.body;
  if (message.media_url || message.type !== 'chat') return `[${message.type === 'chat' ? 'mídia' : message.type}]`;
  return '';
}

export function toChatMessage(message: InboxMessage): ChatMessage {
  return {
    id: message.id,
    direction: message.from_me ? 'outbound' : 'inbound',
    body: bodyOf(message),
    created_at: message.timestamp,
  };
}

export function WhatsAppInbox({
  hooks,
  connectionId,
  initialChatId = null,
  renderChatHeaderExtra,
  onSelectChat,
  fallbackPollMs = 10_000,
  searchPlaceholder = 'Buscar por nome ou telefone',
  emptyThreadsLabel = 'Nenhuma conversa ainda.',
  className,
}: WhatsAppInboxProps) {
  const [searchInput, setSearchInput] = useState('');
  const [query, setQuery] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(initialChatId);

  // Debounce the server-side search so each keystroke is not a request.
  useEffect(() => {
    const timer = setTimeout(() => setQuery(searchInput.trim()), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // A new deep link (lead -> conversation) re-points the selection.
  useEffect(() => {
    if (initialChatId) setSelectedId(initialChatId);
  }, [initialChatId]);

  const stream = hooks.useInboxEvents(connectionId);
  const pollMs = stream.status === 'open' || fallbackPollMs <= 0 ? false : fallbackPollMs;

  const select = useCallback(
    (id: string | null) => {
      setSelectedId(id);
      onSelectChat?.(id);
    },
    [onSelectChat],
  );

  // Latest-render refs keep the adapter's callbacks stable without stale closures.
  const renderExtraRef = useRef(renderChatHeaderExtra);
  renderExtraRef.current = renderChatHeaderExtra;
  const HeaderExtra = useMemo(
    () =>
      function InboxHeaderExtra({ thread }: { scopeId: string | null; thread: ChatThread }) {
        const chat = thread.meta?.chat as InboxChat | undefined;
        return chat && renderExtraRef.current ? <>{renderExtraRef.current(chat)}</> : null;
      },
    [],
  );

  const adapter: ChatWindowAdapter = {
    useThreads: (scopeId) => {
      const list = hooks.useInboxChats(scopeId, { q: query, pollMs });
      // Deep link to a chat outside the loaded pages: ask the server for exactly that one.
      const missing = !!selectedId && !list.showSkeleton && !query && !list.chats.some((c) => c.chat_id === selectedId);
      const lookup = hooks.useInboxChats(scopeId, { q: missing ? selectedId! : '', enabled: missing, pageSize: 5 });
      const chats = useMemo(() => {
        const found = missing ? lookup.chats.filter((c) => c.chat_id === selectedId) : [];
        return [...found, ...list.chats];
      }, [list.chats, lookup.chats, missing]);
      return { data: chats.map(toThread), isLoading: list.showSkeleton, isError: list.isError };
    },
    useMessages: (scopeId, threadId) => {
      const thread = hooks.useInboxMessages(scopeId, threadId, { pollMs });
      return { data: thread.messages.map(toChatMessage), isLoading: thread.showSkeleton, isError: thread.isError };
    },
    useSend: (scopeId, threadId) => {
      const send = hooks.useSendInboxMessage(scopeId, threadId);
      return { mutateAsync: ({ text }) => send.mutateAsync(text), isPending: send.isPending };
    },
    useReadState: (scopeId) => {
      const mark = hooks.useMarkChatRead(scopeId);
      return { markRead: (threadId) => mark.mutate(threadId) };
    },
    useLoadMore: (scopeId, threadId) => {
      const thread = hooks.useInboxMessages(scopeId, threadId, { pollMs });
      return {
        hasMore: !!thread.hasNextPage,
        isLoadingMore: thread.isFetchingNextPage,
        loadMore: () => void thread.fetchNextPage(),
      };
    },
    ...(renderChatHeaderExtra ? { ThreadHeaderExtra: HeaderExtra } : {}),
  };

  const more = hooks.useInboxChats(connectionId, { q: query, pollMs });

  return (
    <ChatWindow
      className={className}
      scopeId={connectionId}
      adapter={adapter}
      emptyThreadsLabel={query ? 'Nenhuma conversa encontrada.' : emptyThreadsLabel}
      selectedThreadId={selectedId}
      onSelectThread={select}
      threadListHeader={
        <div className="relative border-b px-3 py-2">
          <Search className="pointer-events-none absolute left-5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
          <Input
            aria-label="Buscar conversas"
            data-testid="inbox-search"
            className="pl-7"
            placeholder={searchPlaceholder}
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
          />
        </div>
      }
      threadListFooter={
        more.hasNextPage ? (
          <div className="p-2">
            <Button
              variant="ghost"
              size="sm"
              className="w-full"
              data-testid="inbox-load-more-chats"
              disabled={more.isFetchingNextPage}
              onClick={() => void more.fetchNextPage()}
            >
              {more.isFetchingNextPage ? 'Carregando…' : 'Carregar mais conversas'}
            </Button>
          </div>
        ) : null
      }
    />
  );
}

export default WhatsAppInbox;
