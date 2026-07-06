/**
 * ChatWindow — provider-agnostic 2-pane chat organ (thread list + thread
 * panel + composer).
 *
 * Generalizes the WhatsApp chat surface into a reusable seed organ driven
 * entirely by an `adapter` bag of hooks — the same hooks-bag-as-prop
 * pattern as `<NotificationBell hooks={...}/>`. Any messaging surface whose
 * data normalizes to `{id, direction, body, created_at}` messages and
 * `{id, title, ...}` threads can drop this in without ChatWindow ever
 * knowing which provider it is talking to. First two consumers:
 *   - WhatsApp (WAHA) — `products/social-wiring/.../WhatsAppChatWindow.tsx`
 *   - Instagram DMs (Meta Graph) — `products/social-wiring/.../IgDMs.tsx`
 * A 3rd provider only needs to author an adapter — this file never changes.
 *
 * Self-contained — no shadcn dependency. Built on the design-system's own
 * `ui/` primitives (Button, Input, Badge) + Tailwind-only skeleton/avatar/
 * switch so it renders identically regardless of which UI kit a product
 * has installed (mirrors the `NotificationBell` / `IntegrationCard` organs).
 *
 * States rendered (BOTH panes): loading (skeleton) / error / empty /
 * success. Composer disabled while sending; any adapter-thrown error
 * (network failure, or a provider gate such as Meta's App Review) surfaces
 * as an inline banner — never faked as a success.
 *
 * Usage:
 *   <ChatWindow
 *     scopeId={connectionId}
 *     adapter={{ useThreads, useMessages, useSend, useAutoReply }}
 *   />
 *
 * The adapter is responsible for normalizing the provider's raw DTOs
 * (WhatsApp `ChatSummary`/`Message`, Meta `IGConversation`/`IGMessage`, ...)
 * into `ChatThread` / `ChatMessage` — including any provider-specific
 * display logic (e.g. WhatsApp JID stripping) — so this component stays
 * provider-blind.
 */
import { useEffect, useRef, useState, type ReactNode } from "react";
import { AlertCircle, ChevronLeft, Loader2, MessageCircle, Send, User } from "lucide-react";

import { cn } from "../../utils";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { Input } from "../ui/Input";

// ─── Adapter contract ────────────────────────────────────────────────────────

/** Thread (conversation) summary shown in the left-pane list. */
export interface ChatThread {
  id: string;
  /** Display title — already resolved by the adapter (contact name, participant name, ...). */
  title: string;
  lastMessagePreview?: string | null;
  /** ISO datetime string, or null when the thread has no messages yet. */
  lastMessageAt?: string | null;
  lastDirection?: "inbound" | "outbound" | null;
  unreadCount?: number;
}

/** Message rendered in the right-pane thread. */
export interface ChatMessage {
  id: string;
  direction: "inbound" | "outbound";
  /** Already-normalized display text (adapter maps provider-specific fields, e.g. IG's `text`, media fallbacks, ...). */
  body: string;
  /** ISO datetime string. */
  created_at: string;
}

interface ChatAsyncResult<T> {
  data?: T;
  isLoading: boolean;
  isError: boolean;
}

export interface ChatSendResult {
  mutateAsync: (input: { text: string }) => Promise<unknown>;
  isPending: boolean;
}

export interface ChatAutoReplyResult {
  enabled: boolean;
  isPending: boolean;
  onToggle: (enabled: boolean) => void;
}

export interface ChatWindowAdapter {
  /** Thread list for the given scope (WhatsApp connectionId / Meta accountId / ...). */
  useThreads: (scopeId: string | null) => ChatAsyncResult<ChatThread[]>;
  /** Message thread for one (scope, thread) pair. */
  useMessages: (scopeId: string | null, threadId: string | null) => ChatAsyncResult<ChatMessage[]>;
  /**
   * Send mutation for the currently open thread. Any provider-specific
   * rejection (missing recipient, App Review gate, ...) MUST be a thrown
   * `Error` with a user-facing message — ChatWindow surfaces it verbatim,
   * it never fakes a success.
   */
  useSend: (scopeId: string | null, threadId: string | null) => ChatSendResult;
  /** Optional AI auto-reply toggle — omit entirely to hide the control (e.g. Instagram DMs). */
  useAutoReply?: (scopeId: string | null) => ChatAutoReplyResult;
}

export interface ChatWindowProps {
  /** Provider-scoped id (WhatsApp connectionId, Meta accountId, ...). */
  scopeId: string | null;
  adapter: ChatWindowAdapter;
  /** Shown when the thread list has zero threads. */
  emptyThreadsLabel?: string;
  /** Shown as the right-pane placeholder before any thread is selected. */
  emptySelectionLabel?: string;
  className?: string;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** Format ISO datetime as a relative label ("14:35" / "Ontem" / "20/06"). Never "Invalid Date". */
function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  const now = new Date();
  const diffDays = Math.floor((now.getTime() - d.getTime()) / (1000 * 60 * 60 * 24));
  if (diffDays === 0) return d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  if (diffDays === 1) return "Ontem";
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
}

function formatMessageTime(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function Skel({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-muted", className)} />;
}

function AvatarInitials({ name }: { name: string }) {
  const initials = (name || "?").slice(0, 2).toUpperCase();
  return (
    <div
      className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary"
      aria-hidden="true"
    >
      {initials}
    </div>
  );
}

function EmptyState({ icon, label, fullHeight }: { icon: ReactNode; label: string; fullHeight?: boolean }) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 p-6 text-muted-foreground",
        fullHeight && "h-full",
      )}
    >
      {icon}
      <p className="text-xs text-center">{label}</p>
    </div>
  );
}

function ErrorState({ label, fullHeight }: { label: string; fullHeight?: boolean }) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 p-6 text-muted-foreground",
        fullHeight && "h-full",
      )}
    >
      <AlertCircle className="h-5 w-5 text-destructive" />
      <p className="text-xs text-center">{label}</p>
    </div>
  );
}

function ThreadListSkeleton() {
  return (
    <div className="space-y-0" data-testid="chat-thread-list-skeleton">
      {[1, 2, 3].map((i) => (
        <div key={i} className="flex items-center gap-3 px-3 py-3">
          <Skel className="h-9 w-9 flex-shrink-0 rounded-full" />
          <div className="flex-1 space-y-1.5">
            <Skel className="h-3.5 w-28" />
            <Skel className="h-3 w-44" />
          </div>
        </div>
      ))}
    </div>
  );
}

function MessagesSkeleton() {
  return (
    <div className="space-y-3 p-4" data-testid="chat-messages-skeleton">
      {[1, 2, 3].map((i) => (
        <div key={i} className={cn("flex", i % 2 === 0 ? "justify-end" : "justify-start")}>
          <Skel className={cn("h-9 rounded-2xl", i % 2 === 0 ? "w-40" : "w-56")} />
        </div>
      ))}
    </div>
  );
}

function ThreadListItem({
  thread,
  selected,
  onClick,
}: {
  thread: ChatThread;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={`chat-thread-${thread.id}`}
      className={cn(
        "flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors hover:bg-muted/60",
        selected && "bg-muted",
      )}
    >
      <AvatarInitials name={thread.title} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <span className="truncate text-sm font-medium">{thread.title}</span>
          <span className="flex-shrink-0 text-xs text-muted-foreground">
            {relativeTime(thread.lastMessageAt)}
          </span>
        </div>
        <div className="mt-0.5 flex items-center justify-between gap-2">
          <p className="truncate text-xs text-muted-foreground">
            {thread.lastDirection === "outbound" && <span className="mr-1 text-primary">Você:</span>}
            {thread.lastMessagePreview}
          </p>
          {!!thread.unreadCount && thread.unreadCount > 0 && (
            <Badge className="h-5 min-w-5 flex-shrink-0 px-1.5 text-xs">
              {thread.unreadCount > 99 ? "99+" : thread.unreadCount}
            </Badge>
          )}
        </div>
      </div>
    </button>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isOutbound = message.direction === "outbound";
  const bodyText = message.body || "[mensagem vazia]";
  return (
    <div className={cn("mb-2 flex", isOutbound ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[80%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-sm leading-relaxed",
          isOutbound
            ? "rounded-br-md bg-primary text-primary-foreground"
            : "rounded-bl-md bg-muted text-foreground",
        )}
      >
        <p>{bodyText}</p>
        <p className={cn("mt-1 text-[10px]", isOutbound ? "text-primary-foreground/70" : "text-muted-foreground")}>
          {formatMessageTime(message.created_at)}
        </p>
      </div>
    </div>
  );
}

// ─── Thread panel ─────────────────────────────────────────────────────────────

function ThreadPanel({
  scopeId,
  thread,
  adapter,
  onBack,
}: {
  scopeId: string | null;
  thread: ChatThread;
  adapter: ChatWindowAdapter;
  onBack: () => void;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [text, setText] = useState("");
  const [sendError, setSendError] = useState<string | null>(null);

  const { data: messages = [], isLoading: loadingMsgs, isError: errorMsgs } =
    adapter.useMessages(scopeId, thread.id);
  const sendMutation = adapter.useSend(scopeId, thread.id);
  const autoReply = adapter.useAutoReply?.(scopeId);

  useEffect(() => {
    if (!scrollRef.current) return;
    scrollRef.current.scrollTo?.({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages.length, sendMutation.isPending]);

  async function handleSend() {
    const trimmed = text.trim();
    if (!trimmed) return;
    setSendError(null);
    setText("");
    try {
      await sendMutation.mutateAsync({ text: trimmed });
    } catch (err: unknown) {
      setSendError(err instanceof Error ? err.message : "Erro ao enviar. Tente novamente.");
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="flex h-full flex-col" data-testid="chat-thread-panel">
      {/* Header */}
      <div className="flex items-center gap-2 border-b bg-background px-3 py-2">
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 md:hidden"
          onClick={onBack}
          aria-label="Voltar"
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <AvatarInitials name={thread.title} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold">{thread.title}</p>
        </div>
        {autoReply && (
          <div className="flex flex-shrink-0 items-center gap-1.5" title={autoReply.enabled ? "IA respondendo automaticamente." : "Auto-resposta IA desativada."}>
            <span className="hidden text-xs text-muted-foreground sm:inline">IA</span>
            <button
              type="button"
              role="switch"
              aria-checked={autoReply.enabled}
              aria-label="Auto-resposta IA"
              disabled={autoReply.isPending}
              onClick={() => autoReply.onToggle(!autoReply.enabled)}
              data-testid="chat-auto-reply-toggle"
              className={cn(
                "relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors disabled:cursor-not-allowed disabled:opacity-60",
                autoReply.enabled ? "bg-primary" : "bg-muted",
              )}
            >
              <span
                className={cn(
                  "pointer-events-none inline-block h-4 w-4 transform rounded-full bg-background shadow ring-0 transition-transform",
                  autoReply.enabled ? "translate-x-4" : "translate-x-0",
                )}
                aria-hidden="true"
              />
            </button>
          </div>
        )}
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        {loadingMsgs ? (
          <MessagesSkeleton />
        ) : errorMsgs ? (
          <ErrorState label="Erro ao carregar mensagens." fullHeight />
        ) : messages.length === 0 ? (
          <EmptyState icon={<MessageCircle className="h-8 w-8 opacity-30" />} label="Nenhuma mensagem ainda." fullHeight />
        ) : (
          <div className="p-3" data-testid="chat-messages">
            {messages.map((m) => (
              <MessageBubble key={m.id} message={m} />
            ))}
            {sendMutation.isPending && (
              <div className="mb-2 flex justify-end">
                <div className="flex max-w-[80%] items-center gap-2 rounded-2xl bg-primary/50 px-3 py-2 text-sm text-primary-foreground">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  Enviando...
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Composer */}
      <div className="border-t bg-background">
        {sendError && (
          <div className="flex items-center gap-1 px-3 pt-1.5 text-xs text-destructive" data-testid="chat-send-error">
            <AlertCircle className="h-3 w-3" />
            {sendError}
          </div>
        )}
        <div className="flex items-center gap-2 p-2">
          <Input
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Digite uma mensagem..."
            disabled={sendMutation.isPending}
            className="h-8 flex-1 text-sm"
            aria-label="Mensagem"
          />
          <Button
            onClick={handleSend}
            disabled={sendMutation.isPending || !text.trim()}
            variant="primary"
            size="icon"
            className="h-8 w-8"
            aria-label="Enviar mensagem"
          >
            {sendMutation.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Send className="h-3.5 w-3.5" />
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export function ChatWindow({
  scopeId,
  adapter,
  emptyThreadsLabel = "Nenhuma conversa ainda.",
  emptySelectionLabel = "Selecione uma conversa",
  className,
}: ChatWindowProps) {
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);

  const { data: threads = [], isLoading: loadingThreads, isError: errorThreads } =
    adapter.useThreads(scopeId);

  const selectedThread = threads.find((t) => t.id === selectedThreadId) ?? null;
  const showThread = !!selectedThread;

  return (
    <div className={cn("flex flex-1 min-h-0", className)} data-testid="chat-window">
      {/* Left — thread list */}
      <div
        className={cn(
          showThread ? "hidden md:flex" : "flex",
          "w-full flex-shrink-0 flex-col border-r md:w-64",
        )}
      >
        <div className="border-b px-3 py-1.5">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Conversas</p>
        </div>
        <div className="flex-1 overflow-y-auto">
          {loadingThreads ? (
            <ThreadListSkeleton />
          ) : errorThreads ? (
            <ErrorState label="Erro ao carregar conversas." />
          ) : threads.length === 0 ? (
            <EmptyState icon={<MessageCircle className="h-7 w-7 opacity-30" />} label={emptyThreadsLabel} />
          ) : (
            <div>
              {threads.map((thread, idx) => (
                <div key={thread.id}>
                  <ThreadListItem
                    thread={thread}
                    selected={selectedThreadId === thread.id}
                    onClick={() => setSelectedThreadId(thread.id)}
                  />
                  {idx < threads.length - 1 && <div className="ml-14 border-t" />}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Right — thread panel */}
      <div className={cn(showThread ? "flex" : "hidden md:flex", "min-w-0 flex-1 flex-col")}>
        {selectedThread ? (
          <ThreadPanel
            key={selectedThread.id}
            scopeId={scopeId}
            thread={selectedThread}
            adapter={adapter}
            onBack={() => setSelectedThreadId(null)}
          />
        ) : (
          <EmptyState icon={<User className="h-10 w-10 opacity-20" />} label={emptySelectionLabel} fullHeight />
        )}
      </div>
    </div>
  );
}

export default ChatWindow;
