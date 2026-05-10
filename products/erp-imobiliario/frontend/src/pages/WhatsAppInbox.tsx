import { useState, useRef, useEffect } from "react";
import { Input } from "@noctusai/seed/components/ui/input";
import { Button } from "@noctusai/seed/components/ui/button";
import { Badge } from "@noctusai/seed/components/ui/badge";
import { ScrollArea } from "@noctusai/seed/components/ui/scroll-area";
import { useQueryClient } from "@tanstack/react-query";
import {
  useWhatsAppConversations,
  useWhatsAppMessages,
  useWhatsAppConfig,
  useSendWhatsAppMessage,
} from "@/hooks/useWhatsAppInbox";
import {
  MessageSquare, Send, Search, Phone, User, Check, CheckCheck,
  AlertCircle, RefreshCw,
} from "lucide-react";
import { CardListSkeleton } from "@/components/ui/page-skeleton";

function formatTime(dateStr: string) {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  if (diff < 86400000) return d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  if (diff < 604800000) return d.toLocaleDateString("pt-BR", { weekday: "short" });
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
}

function StatusIcon({ status }: { status: string }) {
  if (status === "read") return <CheckCheck className="h-3 w-3 text-blue-500" />;
  if (status === "delivered") return <CheckCheck className="h-3 w-3 text-muted-foreground" />;
  if (status === "sent") return <Check className="h-3 w-3 text-muted-foreground" />;
  if (status === "failed") return <AlertCircle className="h-3 w-3 text-destructive" />;
  return null;
}

export default function WhatsAppInbox() {
  const [selectedPhone, setSelectedPhone] = useState<string | null>(null);
  const [messageText, setMessageText] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();

  const { data: conversations = [], isLoading: loadingConversations } = useWhatsAppConversations();
  const { data: messages = [], isLoading: loadingMessages } = useWhatsAppMessages(selectedPhone);
  const { data: configStatus } = useWhatsAppConfig();
  const sendMessage = useSendWhatsAppMessage(selectedPhone);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const filteredConversations = conversations.filter((c) =>
    c.phone.includes(searchTerm) || (c.cliente_nome || "").toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleSend = () => {
    if (!selectedPhone || !messageText.trim()) return;
    sendMessage.mutate(
      { phone: selectedPhone, message: messageText.trim() },
      { onSuccess: () => setMessageText("") },
    );
  };

  return (
    <div className="h-[calc(100vh-4rem)] flex flex-col">
      <div className="flex items-center justify-between p-4 border-b">
        <div className="flex items-center gap-2">
          <MessageSquare className="h-5 w-5 text-green-600" />
          <h1 className="text-lg font-semibold">WhatsApp</h1>
          <Badge variant="outline" className="text-xs">
            {conversations.length} conversas
          </Badge>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => queryClient.invalidateQueries({ queryKey: ["whatsapp-conversations"] })}
          >
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Conversation list */}
        <div className="w-80 border-r flex flex-col">
          <div className="p-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Buscar conversa..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-9"
              />
            </div>
          </div>
          <ScrollArea className="flex-1">
            {loadingConversations ? (
              <div className="p-4"><CardListSkeleton count={3} /></div>
            ) : filteredConversations.length === 0 ? (
              <div className="p-4 text-center text-sm text-muted-foreground">
                Nenhuma conversa encontrada
              </div>
            ) : (
              filteredConversations.map((conv) => (
                <button
                  key={conv.phone}
                  onClick={() => setSelectedPhone(conv.phone)}
                  className={`w-full text-left px-3 py-3 hover:bg-accent transition-colors border-b ${
                    selectedPhone === conv.phone ? "bg-accent" : ""
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <div className="h-10 w-10 rounded-full bg-green-100 dark:bg-green-900 flex items-center justify-center shrink-0">
                        <User className="h-5 w-5 text-green-700 dark:text-green-300" />
                      </div>
                      <div className="min-w-0">
                        <p className="font-medium text-sm truncate">
                          {conv.cliente_nome || conv.phone}
                        </p>
                        <p className="text-xs text-muted-foreground truncate">
                          {conv.last_message}
                        </p>
                      </div>
                    </div>
                    <div className="flex flex-col items-end shrink-0 gap-1">
                      <span className="text-[10px] text-muted-foreground">
                        {formatTime(conv.last_time)}
                      </span>
                      {conv.unread > 0 && (
                        <Badge className="bg-green-600 text-white text-[10px] h-5 w-5 flex items-center justify-center p-0 rounded-full">
                          {conv.unread}
                        </Badge>
                      )}
                    </div>
                  </div>
                </button>
              ))
            )}
          </ScrollArea>
        </div>

        {/* Chat area */}
        <div className="flex-1 flex flex-col">
          {!selectedPhone ? (
            <div className="flex-1 flex items-center justify-center text-muted-foreground">
              <div className="text-center">
                <MessageSquare className="h-16 w-16 mx-auto mb-4 opacity-20" />
                <p>Selecione uma conversa para começar</p>
              </div>
            </div>
          ) : (
            <>
              {/* Chat header */}
              <div className="px-4 py-3 border-b flex items-center gap-3">
                <div className="h-9 w-9 rounded-full bg-green-100 dark:bg-green-900 flex items-center justify-center">
                  <User className="h-4 w-4 text-green-700 dark:text-green-300" />
                </div>
                <div>
                  <p className="font-medium text-sm">{selectedPhone}</p>
                  <p className="text-xs text-muted-foreground flex items-center gap-1">
                    <Phone className="h-3 w-3" /> WhatsApp
                  </p>
                </div>
              </div>

              {/* Messages */}
              <ScrollArea className="flex-1 p-4">
                <div className="space-y-3 max-w-2xl mx-auto">
                  {loadingMessages ? (
                    <CardListSkeleton count={3} />
                  ) : messages.length === 0 ? (
                    <p className="text-center text-sm text-muted-foreground">
                      Nenhuma mensagem ainda
                    </p>
                  ) : (
                    messages.map((msg) => (
                      <div
                        key={msg.id}
                        className={`flex ${msg.direction === "sent" ? "justify-end" : "justify-start"}`}
                      >
                        <div
                          className={`max-w-[75%] rounded-lg px-3 py-2 ${
                            msg.direction === "sent"
                              ? "bg-green-600 text-white"
                              : "bg-muted"
                          }`}
                        >
                          <p className="text-sm whitespace-pre-wrap">{msg.message}</p>
                          <div className={`flex items-center gap-1 mt-1 ${
                            msg.direction === "sent" ? "justify-end" : ""
                          }`}>
                            <span className={`text-[10px] ${
                              msg.direction === "sent" ? "text-green-200" : "text-muted-foreground"
                            }`}>
                              {formatTime(msg.created_at)}
                            </span>
                            {msg.direction === "sent" && <StatusIcon status={msg.status} />}
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                  <div ref={messagesEndRef} />
                </div>
              </ScrollArea>

              {/* Message input */}
              <div className="p-3 border-t">
                <div className="flex gap-2 max-w-2xl mx-auto">
                  <Input
                    placeholder="Digite uma mensagem..."
                    value={messageText}
                    onChange={(e) => setMessageText(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
                    className="flex-1"
                  />
                  <Button
                    onClick={handleSend}
                    disabled={!messageText.trim() || sendMessage.isPending}
                    className="bg-green-600 hover:bg-green-700"
                  >
                    <Send className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
