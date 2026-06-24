/**
 * WhatsApp Chat — WhatsApp-Web-style chat surface.
 *
 * Layout:
 *   - Connection selector at the top (uses existing useWhatsAppConnections)
 *   - Two-pane: left = conversation list, right = thread + composer
 *   - Auto-reply (IA) toggle in the thread header bound to useSetAutoReply
 *
 * Polling v1: all live reads are encapsulated in useWhatsAppChats /
 * useWhatsAppChatMessages. The WS-v2 upgrade only touches hook internals.
 */
import { useEffect, useRef, useState } from "react";
import {
  Loader2,
  MessageCircle,
  Send,
  User,
  AlertCircle,
  ChevronLeft,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Avatar } from "@/components/ui/avatar";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

import {
  useWhatsAppConnections,
  type WhatsAppConnectionLine,
} from "@/hooks/useWhatsAppConnections";
import {
  useWhatsAppChats,
  useWhatsAppChatMessages,
  useSendWhatsAppMessage,
  useSetAutoReply,
  type ChatSummary,
  type Message,
} from "@/hooks/useWhatsAppChats";

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * Format ISO datetime as a relative label (e.g., "14:35", "Ontem", "20/06").
 * Returns "" when iso is null, empty, or not a valid date — never "Invalid Date".
 */
function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";

  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) {
    return d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  }
  if (diffDays === 1) return "Ontem";
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
}

/**
 * Return the display name for a contact.
 * The backend now sets contact = resolved name (e.g. "João Raphael") when
 * available, otherwise the raw JID (e.g. "5511999998888@c.us").
 * Strip the JID suffix only when the contact looks like a JID.
 */
function displayContact(contact: string): string {
  // If the value contains "@" it is a JID — strip the domain suffix
  if (contact.includes("@")) {
    return contact.replace(/@.*$/, "");
  }
  return contact;
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function AvatarInitials({ name }: { name: string }) {
  const initials = name.slice(0, 2).toUpperCase();
  return (
    <Avatar className="h-10 w-10 flex-shrink-0">
      <div className="flex h-full w-full items-center justify-center rounded-full bg-primary/10 text-primary text-sm font-semibold">
        {initials}
      </div>
    </Avatar>
  );
}

function ChatListItem({
  chat,
  selected,
  onClick,
}: {
  chat: ChatSummary;
  selected: boolean;
  onClick: () => void;
}) {
  const contact = displayContact(chat.contact);
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full flex items-center gap-3 px-3 py-3 text-left hover:bg-muted/60 transition-colors ${
        selected ? "bg-muted" : ""
      }`}
    >
      <AvatarInitials name={contact} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <span className="font-medium text-sm truncate">{contact}</span>
          <span className="text-xs text-muted-foreground flex-shrink-0">
            {relativeTime(chat.last_message_at)}
          </span>
        </div>
        <div className="flex items-center justify-between gap-2 mt-0.5">
          <p className="text-xs text-muted-foreground truncate">
            {chat.last_direction === "outbound" && (
              <span className="text-primary mr-1">Você:</span>
            )}
            {chat.last_message}
          </p>
          {chat.unread > 0 && (
            <Badge className="h-5 min-w-5 px-1.5 text-xs flex-shrink-0 bg-primary text-primary-foreground">
              {chat.unread > 99 ? "99+" : chat.unread}
            </Badge>
          )}
        </div>
      </div>
    </button>
  );
}

function MessageBubble({ message }: { message: Message }) {
  const isOutbound = message.direction === "outbound";
  const bodyText =
    message.body ||
    (message.structured_payload
      ? "[mídia]"
      : "[mensagem vazia]");

  return (
    <div className={`flex ${isOutbound ? "justify-end" : "justify-start"} mb-2`}>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-2 whitespace-pre-wrap text-sm leading-relaxed ${
          isOutbound
            ? "bg-primary text-primary-foreground rounded-br-md"
            : "bg-muted text-foreground rounded-bl-md"
        }`}
      >
        <p>{bodyText}</p>
        <p
          className={`text-[10px] mt-1 ${
            isOutbound ? "text-primary-foreground/70" : "text-muted-foreground"
          }`}
        >
          {new Date(message.created_at).toLocaleTimeString("pt-BR", {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </p>
      </div>
    </div>
  );
}

function MessagesSkeleton() {
  return (
    <div className="p-4 space-y-3">
      {[1, 2, 3].map((i) => (
        <div
          key={i}
          className={`flex ${i % 2 === 0 ? "justify-end" : "justify-start"}`}
        >
          <Skeleton className={`h-10 rounded-2xl ${i % 2 === 0 ? "w-48" : "w-64"}`} />
        </div>
      ))}
    </div>
  );
}

function ChatListSkeleton() {
  return (
    <div className="space-y-0">
      {[1, 2, 3, 4].map((i) => (
        <div key={i} className="flex items-center gap-3 px-3 py-3">
          <Skeleton className="h-10 w-10 rounded-full flex-shrink-0" />
          <div className="flex-1 space-y-1.5">
            <Skeleton className="h-3.5 w-32" />
            <Skeleton className="h-3 w-48" />
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Thread panel ─────────────────────────────────────────────────────────────

function ThreadPanel({
  connection,
  chat,
  onBack,
}: {
  connection: WhatsAppConnectionLine & { auto_reply_enabled: boolean };
  chat: ChatSummary;
  onBack: () => void;
}) {
  const contact = displayContact(chat.contact);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [text, setText] = useState("");
  const [sendError, setSendError] = useState<string | null>(null);

  const {
    data: messages = [],
    isLoading: loadingMsgs,
    isError: errorMsgs,
  } = useWhatsAppChatMessages(connection.id, chat.chat_id);

  const sendMutation = useSendWhatsAppMessage(connection.id, chat.chat_id);
  const autoReplyMutation = useSetAutoReply(connection.id);

  // Auto-scroll to newest message
  useEffect(() => {
    if (!scrollRef.current) return;
    // scrollTo may be undefined in jsdom (vitest) — guard with optional call
    scrollRef.current.scrollTo?.({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages.length, sendMutation.isPending]);

  async function handleSend() {
    const trimmed = text.trim();
    if (!trimmed) return;
    setSendError(null);
    setText("");
    try {
      await sendMutation.mutateAsync({ text: trimmed });
    } catch (err: unknown) {
      const msg =
        err instanceof Error
          ? err.message
          : "Erro ao enviar mensagem. Tente novamente.";
      setSendError(msg);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Thread header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b bg-background">
        <Button
          variant="ghost"
          size="icon"
          className="md:hidden h-8 w-8"
          onClick={onBack}
          aria-label="Voltar para lista"
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <AvatarInitials name={contact} />
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-sm">{contact}</p>
          <p className="text-xs text-muted-foreground">{chat.chat_id}</p>
        </div>

        {/* Auto-reply toggle */}
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <div className="flex items-center gap-2 flex-shrink-0">
                <span className="text-xs text-muted-foreground hidden sm:inline">
                  Auto-resposta (IA)
                </span>
                <Switch
                  checked={connection.auto_reply_enabled}
                  disabled={autoReplyMutation.isPending}
                  onCheckedChange={(enabled) => {
                    autoReplyMutation.mutate({ enabled });
                  }}
                  aria-label="Ativar ou desativar auto-resposta com IA"
                />
              </div>
            </TooltipTrigger>
            <TooltipContent>
              {connection.auto_reply_enabled
                ? "IA respondendo automaticamente. Desativar para responder manualmente."
                : "OFF — somente suas respostas manuais são enviadas."}
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>

      {/* Messages area */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        {loadingMsgs ? (
          <MessagesSkeleton />
        ) : errorMsgs ? (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-muted-foreground p-8">
            <AlertCircle className="h-8 w-8 text-destructive" />
            <p className="text-sm text-center">
              Erro ao carregar mensagens. As mensagens serão atualizadas automaticamente.
            </p>
          </div>
        ) : messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-muted-foreground p-8">
            <MessageCircle className="h-10 w-10 opacity-30" />
            <p className="text-sm">Nenhuma mensagem ainda.</p>
          </div>
        ) : (
          <div className="p-4">
            {messages.map((m) => (
              <MessageBubble key={m.id} message={m} />
            ))}
            {sendMutation.isPending && (
              <div className="flex justify-end mb-2">
                <div className="max-w-[80%] rounded-2xl px-4 py-2 bg-primary/50 text-primary-foreground text-sm flex items-center gap-2">
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
          <div className="px-4 pt-2 text-xs text-destructive flex items-center gap-1">
            <AlertCircle className="h-3 w-3" />
            {sendError}
          </div>
        )}
        <div className="p-3 flex items-center gap-2">
          <Input
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Digite uma mensagem..."
            disabled={sendMutation.isPending}
            className="flex-1"
            aria-label="Mensagem"
          />
          <Button
            onClick={handleSend}
            disabled={sendMutation.isPending || !text.trim()}
            size="icon"
            aria-label="Enviar mensagem"
          >
            {sendMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function WhatsAppChat() {
  const {
    data: connections = [],
    isLoading: loadingConns,
    isError: errorConns,
  } = useWhatsAppConnections();

  const [selectedConnId, setSelectedConnId] = useState<string | null>(null);
  const [selectedChatId, setSelectedChatId] = useState<string | null>(null);

  // Default-select first connection when loaded
  useEffect(() => {
    if (connections.length > 0 && !selectedConnId) {
      setSelectedConnId(connections[0].id);
    }
    // Clear selection if chosen conn disappears
    if (
      selectedConnId &&
      connections.length > 0 &&
      !connections.find((c) => c.id === selectedConnId)
    ) {
      setSelectedConnId(connections[0].id);
      setSelectedChatId(null);
    }
  }, [connections, selectedConnId]);

  const selectedConn = connections.find((c) => c.id === selectedConnId) as
    | (WhatsAppConnectionLine & { auto_reply_enabled: boolean })
    | undefined;

  const {
    data: chats = [],
    isLoading: loadingChats,
    isError: errorChats,
  } = useWhatsAppChats(selectedConnId);

  const selectedChat = chats.find((c) => c.chat_id === selectedChatId);

  // On mobile: show thread only when chat is selected
  const showThread = !!selectedChat;

  if (loadingConns) {
    return (
      <div className="flex items-center justify-center h-64 gap-3 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" />
        <span className="text-sm">Carregando conexões...</span>
      </div>
    );
  }

  if (errorConns) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3 text-muted-foreground">
        <AlertCircle className="h-8 w-8 text-destructive" />
        <p className="text-sm">Erro ao carregar conexões. Recarregue a página.</p>
      </div>
    );
  }

  if (connections.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-4 text-muted-foreground">
        <Smartphone className="h-12 w-12 opacity-30" />
        <div className="text-center">
          <p className="text-sm font-medium">Nenhuma conexão WhatsApp</p>
          <p className="text-xs mt-1">
            Vá para{" "}
            <a href="/conexoes" className="underline text-primary">
              Conexões
            </a>{" "}
            para adicionar uma conexão.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] -mx-4 -mt-4">
      {/* Connection selector bar */}
      <div className="flex items-center gap-2 px-4 py-2 border-b bg-background overflow-x-auto flex-shrink-0">
        <span className="text-xs text-muted-foreground whitespace-nowrap">Conexão:</span>
        {connections.map((conn) => (
          <Button
            key={conn.id}
            variant={selectedConnId === conn.id ? "default" : "outline"}
            size="sm"
            onClick={() => {
              setSelectedConnId(conn.id);
              setSelectedChatId(null);
            }}
            className="whitespace-nowrap text-xs h-7"
          >
            {conn.label}
          </Button>
        ))}
      </div>

      {/* Two-pane layout */}
      <div className="flex flex-1 min-h-0">
        {/* Left — conversation list */}
        <div
          className={`${
            showThread ? "hidden md:flex" : "flex"
          } flex-col w-full md:w-80 border-r flex-shrink-0`}
        >
          <div className="px-3 py-2 border-b">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Conversas
            </p>
          </div>
          <div className="flex-1 overflow-y-auto">
            {loadingChats ? (
              <ChatListSkeleton />
            ) : errorChats ? (
              <div className="flex flex-col items-center justify-center h-full gap-3 p-6 text-muted-foreground">
                <AlertCircle className="h-6 w-6 text-destructive" />
                <p className="text-xs text-center">
                  Erro ao carregar conversas. Atualizando automaticamente...
                </p>
              </div>
            ) : chats.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full gap-3 p-6 text-muted-foreground">
                <MessageCircle className="h-8 w-8 opacity-30" />
                <p className="text-xs text-center">
                  Nenhuma conversa ainda nesta conexão.
                </p>
              </div>
            ) : (
              <div>
                {chats.map((chat, idx) => (
                  <div key={chat.chat_id}>
                    <ChatListItem
                      chat={chat}
                      selected={selectedChatId === chat.chat_id}
                      onClick={() => setSelectedChatId(chat.chat_id)}
                    />
                    {idx < chats.length - 1 && (
                      <Separator className="ml-16" />
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right — thread panel */}
        <div
          className={`${
            showThread ? "flex" : "hidden md:flex"
          } flex-col flex-1 min-w-0`}
        >
          {selectedChat && selectedConn ? (
            <ThreadPanel
              connection={selectedConn}
              chat={selectedChat}
              onBack={() => setSelectedChatId(null)}
            />
          ) : (
            <div className="flex flex-col items-center justify-center h-full gap-3 text-muted-foreground">
              <User className="h-12 w-12 opacity-20" />
              <p className="text-sm">Selecione uma conversa para começar</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// Needed for the empty-state icon (imported inline to avoid duplicate lucide import block)
function Smartphone({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <rect width="14" height="20" x="5" y="2" rx="2" ry="2" />
      <path d="M12 18h.01" />
    </svg>
  );
}
