/**
 * Chat page — talk to the OpenAI tool-calling agent from the platform.
 *
 * Same backend brain as the WhatsApp inbound flow. The user types a
 * property code + (optionally) attaches a video file, and the agent
 * fetches CRM data, prepares an upload, asks for confirmation, and
 * queues the YouTube publish.
 *
 * Auth: intentionally open for now (per the product brief). When real
 * auth lands, the hook starts forwarding the supabase token.
 */
import { useEffect, useRef, useState } from "react";
import {
  Loader2,
  Paperclip,
  RefreshCw,
  Send,
  Sparkles,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";

import { useChat, type ChatHistoryItem } from "@/hooks/useChat";

function MessageBubble({ message }: { message: ChatHistoryItem }) {
  const isUser = message.role === "user";
  return (
    <div
      className={`flex ${isUser ? "justify-end" : "justify-start"} mb-3`}
    >
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-2 whitespace-pre-wrap text-sm leading-relaxed ${
          isUser
            ? "bg-primary text-primary-foreground rounded-br-md"
            : "bg-muted text-foreground rounded-bl-md"
        }`}
      >
        {message.content}
      </div>
    </div>
  );
}

function PendingPanel({
  pending,
}: {
  pending: ReturnType<typeof useChat>["pending"];
}) {
  if (!pending || !pending.found) return null;
  const stateLabels: Record<string, string> = {
    awaiting_confirmation: "Aguardando confirmacao",
    awaiting_manual_title: "Aguardando titulo manual",
    processing: "Processando upload",
    idle: "Inativo",
  };
  return (
    <Card className="border-dashed">
      <CardHeader className="pb-2">
        <CardTitle className="text-base flex items-center gap-2">
          <Sparkles className="h-4 w-4" />
          Upload em preparacao
        </CardTitle>
        <CardDescription>
          {stateLabels[pending.state || ""] || pending.state}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-1 text-sm">
        <div>
          <span className="text-muted-foreground">Codigo:</span>{" "}
          <Badge variant="outline">{pending.product_code}</Badge>
        </div>
        {pending.title && (
          <div>
            <span className="text-muted-foreground">Titulo:</span>{" "}
            {pending.title}
          </div>
        )}
        {pending.video_filename && (
          <div>
            <span className="text-muted-foreground">Arquivo:</span>{" "}
            {pending.video_filename}
            {pending.video_size_bytes
              ? ` (${(pending.video_size_bytes / (1024 * 1024)).toFixed(1)} MB)`
              : ""}
          </div>
        )}
        {pending.drive_url && (
          <div className="truncate">
            <span className="text-muted-foreground">Link:</span>{" "}
            {pending.drive_url}
          </div>
        )}
        <div>
          <span className="text-muted-foreground">Privacidade:</span>{" "}
          <Badge variant="secondary">
            {pending.privacy_status || "private"}
          </Badge>
        </div>
      </CardContent>
    </Card>
  );
}

export default function Chat() {
  const { sessionId, messages, pending, sending, error, sendMessage, reset } =
    useChat();
  const [text, setText] = useState("");
  const [attachment, setAttachment] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!scrollRef.current) return;
    scrollRef.current.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages.length, sending]);

  async function handleSend() {
    if (!text.trim() && !attachment) return;
    const sendText = text;
    const sendFile = attachment;
    setText("");
    setAttachment(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
    await sendMessage(sendText, sendFile);
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="container mx-auto py-6 max-w-4xl space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold flex items-center gap-2">
            <Sparkles className="h-6 w-6 text-primary" />
            Agente NoctusAI
          </h1>
          <p className="text-sm text-muted-foreground">
            Envie um codigo de imovel (ONExxxx) + video (arquivo ou link
            do Google Drive). O agente busca os dados no CRM, monta o
            titulo/descricao e dispara o upload no YouTube.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {sessionId && (
            <Badge variant="outline" className="text-xs">
              {sessionId.slice(0, 14)}...
            </Badge>
          )}
          <Button variant="ghost" size="sm" onClick={reset} disabled={sending}>
            <RefreshCw className="h-4 w-4 mr-1" />
            Resetar
          </Button>
        </div>
      </div>

      <PendingPanel pending={pending} />

      <Card>
        <CardContent className="p-0">
          <div
            ref={scrollRef}
            className="h-[480px] overflow-y-auto"
          >
            <div className="p-4">
              {messages.length === 0 ? (
                <div className="text-center text-sm text-muted-foreground py-12">
                  Diga algo como: <em>"ONE5555"</em> e anexe o video para
                  iniciar.
                </div>
              ) : (
                messages.map((m, i) => (
                  <MessageBubble key={i} message={m} />
                ))
              )}
              {sending && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Pensando...
                </div>
              )}
            </div>
          </div>

          <Separator />

          {error && (
            <div className="px-4 py-2 text-sm text-destructive">
              {error}
            </div>
          )}

          <div className="p-3 flex items-center gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept="video/*"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0] || null;
                setAttachment(f);
              }}
            />
            <Button
              variant="ghost"
              size="icon"
              onClick={() => fileInputRef.current?.click()}
              disabled={sending}
              title="Anexar video"
            >
              <Paperclip className="h-4 w-4" />
            </Button>
            {attachment && (
              <Badge variant="secondary" className="gap-1">
                {attachment.name.length > 24
                  ? `${attachment.name.slice(0, 24)}...`
                  : attachment.name}
                <button
                  type="button"
                  onClick={() => setAttachment(null)}
                  className="ml-1 inline-flex"
                  aria-label="Remover anexo"
                >
                  <X className="h-3 w-3" />
                </button>
              </Badge>
            )}
            <Input
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="ONExxxx + link do Drive, ou anexe o arquivo..."
              disabled={sending}
              className="flex-1"
            />
            <Button
              onClick={handleSend}
              disabled={sending || (!text.trim() && !attachment)}
            >
              {sending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
