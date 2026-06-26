/**
 * WhatsAppChatWindow — embeddable WhatsApp chat surface scoped to ONE connection.
 *
 * Drop-in for any context that already has a connectionId (the ClienteModal
 * Chat tab, a future inline panel, etc.). It does NOT contain a connection
 * picker — that's the caller's responsibility.
 *
 * Data layer: same hooks as WhatsAppChat.tsx (useWhatsAppChats,
 * useWhatsAppChatMessages, useSendWhatsAppMessage, useSetAutoReply).
 * UI layout: two-pane, adapts to the container's height via flex / min-h-0.
 *
 * Props:
 *   connectionId      — WAHA connection to show (required).
 *   autoReplyEnabled  — initial auto-reply state from the connection object;
 *                       the component reflects live-toggle results automatically.
 *   className         — optional extra class on the root div.
 */
import { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  ChevronLeft,
  Loader2,
  MessageCircle,
  Send,
  User,
} from "lucide-react";

import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

import {
  useWhatsAppChats,
  useWhatsAppChatMessages,
  useSendWhatsAppMessage,
  useSetAutoReply,
  type ChatSummary,
  type Message,
} from "@/hooks/useWhatsAppChats";

// ─── Helpers ─────────────────────────────────────────────────────────────────

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

function displayContact(contact: string): string {
  if (contact.includes("@")) return contact.replace(/@.*$/, "");
  return contact;
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function AvatarInitials({ name }: { name: string }) {
  const initials = name.slice(0, 2).toUpperCase();
  return (
    <Avatar className="h-9 w-9 flex-shrink-0">
      <div className="flex h-full w-full items-center justify-center rounded-full bg-primary/10 text-primary text-xs font-semibold">
        {initials}
      </div>
    </Avatar>
  );
}

function ChatListSkeleton() {
  return (
    <div className="space-y-0" data-testid="chat-list-skeleton">
      {[1, 2, 3].map((i) => (
        <div key={i} className="flex items-center gap-3 px-3 py-3">
          <Skeleton className="h-9 w-9 rounded-full flex-shrink-0" />
          <div className="flex-1 space-y-1.5">
            <Skeleton className="h-3.5 w-28" />
            <Skeleton className="h-3 w-44" />
          </div>
        </div>
      ))}
    </div>
  );
}

function MessagesSkeleton() {
  return (
    <div className="p-4 space-y-3" data-testid="messages-skeleton">
      {[1, 2, 3].map((i) => (
        <div key={i} className={`flex ${i % 2 === 0 ? "justify-end" : "justify-start"}`}>
          <Skeleton className={`h-9 rounded-2xl ${i % 2 === 0 ? "w-40" : "w-56"}`} />
        </div>
      ))}
    </div>
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
      className={`w-full flex items-center gap-3 px-3 py-2.5 text-left hover:bg-muted/60 transition-colors ${
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
  const bodyText = message.body || (message.structured_payload ? "[mídia]" : "[mensagem vazia]");
  return (
    <div className={`flex ${isOutbound ? "justify-end" : "justify-start"} mb-2`}>
      <div
        className={`max-w-[80%] rounded-2xl px-3 py-2 whitespace-pre-wrap text-sm leading-relaxed ${
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

// ─── Thread panel ─────────────────────────────────────────────────────────────

function ThreadPanel({
  connectionId,
  autoReplyEnabled,
  chat,
  onBack,
}: {
  connectionId: string;
  autoReplyEnabled: boolean;
  chat: ChatSummary;
  onBack: () => void;
}) {
  const contact = displayContact(chat.contact);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [text, setText] = useState("");
  const [sendError, setSendError] = useState<string | null>(null);

  const { data: messages = [], isLoading: loadingMsgs, isError: errorMsgs } =
    useWhatsAppChatMessages(connectionId, chat.chat_id);
  const sendMutation = useSendWhatsAppMessage(connectionId, chat.chat_id);
  const autoReplyMutation = useSetAutoReply(connectionId);

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
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b bg-background">
        <Button variant="ghost" size="icon" className="md:hidden h-7 w-7" onClick={onBack} aria-label="Voltar">
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <AvatarInitials name={contact} />
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-sm truncate">{contact}</p>
          <p className="text-[10px] text-muted-foreground truncate">{chat.chat_id}</p>
        </div>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <div className="flex items-center gap-1.5 flex-shrink-0">
                <span className="text-xs text-muted-foreground hidden sm:inline">IA</span>
                <Switch
                  checked={autoReplyEnabled}
                  disabled={autoReplyMutation.isPending}
                  onCheckedChange={(enabled) => autoReplyMutation.mutate({ enabled })}
                  aria-label="Auto-resposta IA"
                />
              </div>
            </TooltipTrigger>
            <TooltipContent>
              {autoReplyEnabled ? "IA respondendo automaticamente." : "Auto-resposta IA desativada."}
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        {loadingMsgs ? (
          <MessagesSkeleton />
        ) : errorMsgs ? (
          <div className="flex flex-col items-center justify-center h-full gap-2 text-muted-foreground p-6">
            <AlertCircle className="h-6 w-6 text-destructive" />
            <p className="text-xs text-center">Erro ao carregar mensagens.</p>
          </div>
        ) : messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-2 text-muted-foreground p-6">
            <MessageCircle className="h-8 w-8 opacity-30" />
            <p className="text-xs">Nenhuma mensagem ainda.</p>
          </div>
        ) : (
          <div className="p-3">
            {messages.map((m) => <MessageBubble key={m.id} message={m} />)}
            {sendMutation.isPending && (
              <div className="flex justify-end mb-2">
                <div className="max-w-[80%] rounded-2xl px-3 py-2 bg-primary/50 text-primary-foreground text-sm flex items-center gap-2">
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
          <div className="px-3 pt-1.5 text-xs text-destructive flex items-center gap-1">
            <AlertCircle className="h-3 w-3" />
            {sendError}
          </div>
        )}
        <div className="p-2 flex items-center gap-2">
          <Input
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Digite uma mensagem..."
            disabled={sendMutation.isPending}
            className="flex-1 h-8 text-sm"
            aria-label="Mensagem"
          />
          <Button
            onClick={handleSend}
            disabled={sendMutation.isPending || !text.trim()}
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
  const [selectedChatId, setSelectedChatId] = useState<string | null>(null);

  const {
    data: chats = [],
    isLoading: loadingChats,
    isError: errorChats,
  } = useWhatsAppChats(connectionId);

  const selectedChat = chats.find((c) => c.chat_id === selectedChatId) ?? null;
  const showThread = !!selectedChat;

  return (
    <div
      className={`flex flex-1 min-h-0 ${className ?? ""}`}
      data-testid="wa-chat-window"
    >
      {/* Left — conversation list */}
      <div
        className={`${
          showThread ? "hidden md:flex" : "flex"
        } flex-col w-full md:w-64 border-r flex-shrink-0`}
      >
        <div className="px-3 py-1.5 border-b">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Conversas
          </p>
        </div>
        <div className="flex-1 overflow-y-auto">
          {loadingChats ? (
            <ChatListSkeleton />
          ) : errorChats ? (
            <div className="flex flex-col items-center justify-center h-full gap-2 p-4 text-muted-foreground">
              <AlertCircle className="h-5 w-5 text-destructive" />
              <p className="text-xs text-center">Erro ao carregar conversas.</p>
            </div>
          ) : chats.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full gap-2 p-4 text-muted-foreground">
              <MessageCircle className="h-7 w-7 opacity-30" />
              <p className="text-xs text-center">Nenhuma conversa nesta conexão.</p>
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
                  {idx < chats.length - 1 && <Separator className="ml-14" />}
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
        {selectedChat ? (
          <ThreadPanel
            connectionId={connectionId}
            autoReplyEnabled={autoReplyEnabled}
            chat={selectedChat}
            onBack={() => setSelectedChatId(null)}
          />
        ) : (
          <div className="flex flex-col items-center justify-center h-full gap-2 text-muted-foreground">
            <User className="h-10 w-10 opacity-20" />
            <p className="text-sm">Selecione uma conversa</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default WhatsAppChatWindow;
