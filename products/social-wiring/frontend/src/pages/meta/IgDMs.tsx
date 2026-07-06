/**
 * IgDMs — Instagram "DMs" subtab: a MINIMAL 2-pane chat surface
 * (conversations list / message thread + send).
 *
 * Deliberately thin — Wave 4 extracts a shared `ChatWindow` (see
 * `WhatsAppChat.tsx` for the full-featured sibling: avatars, relative-time
 * labels, auto-reply toggle, etc.) and swaps this pane in wholesale. The
 * `IGMessage` DTO (`direction: "inbound"|"outbound"`) already mirrors the
 * WhatsApp `Message` DTO shape for that swap (see hooks/useMeta.ts header).
 *
 * Sending requires a `recipient_id` per the Wave 3 contract body shape
 * (`{recipient_id, text}`) — resolved from the selected conversation's
 * `participant_id`.
 */
import { useState } from "react";
import { CircleAlert, Loader2, MessageCircle, Send } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";

import {
  isAppReviewGate,
  useActiveMetaAccountId,
  useIgConversations,
  useIgMessages,
  useSendIgMessage,
} from "@/hooks/useMeta";
import { AppReviewNotice } from "./AppReviewNotice";

function ConversationList({
  accountId,
  selectedId,
  onSelect,
}: {
  accountId: string;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const { data, isLoading, isError } = useIgConversations(accountId);
  const conversations = data?.conversations ?? [];

  if (isLoading) {
    return (
      <div className="space-y-2 p-3" data-testid="ig-dm-list-loading">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-14 w-full rounded-md" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div
        className="flex items-center gap-2 p-4 text-sm text-destructive"
        data-testid="ig-dm-list-error"
      >
        <CircleAlert className="h-4 w-4 shrink-0" />
        Erro ao carregar conversas.
      </div>
    );
  }

  if (conversations.length === 0) {
    return (
      <div
        className="p-6 text-center text-sm text-muted-foreground"
        data-testid="ig-dm-list-empty"
      >
        Nenhuma conversa por enquanto.
      </div>
    );
  }

  return (
    <ul className="divide-y" data-testid="ig-dm-list">
      {conversations.map((c) => (
        <li key={c.id}>
          <button
            type="button"
            data-testid={`ig-dm-conversation-${c.id}`}
            onClick={() => onSelect(c.id)}
            className={`flex w-full flex-col items-start gap-0.5 px-3 py-2.5 text-left text-sm hover:bg-muted/50 ${
              selectedId === c.id ? "bg-muted" : ""
            }`}
          >
            <span className="font-medium">{c.participant_name ?? "Contato"}</span>
            <span className="line-clamp-1 text-xs text-muted-foreground">
              {c.snippet ?? "—"}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

function MessageThread({ accountId, conversationId, recipientId }: {
  accountId: string;
  conversationId: string;
  recipientId: string | null;
}) {
  const { data, isLoading, isError } = useIgMessages(accountId, conversationId);
  const send = useSendIgMessage(accountId, conversationId);
  const [text, setText] = useState("");

  const gate = send.data && isAppReviewGate(send.data) ? send.data : null;
  const messages = data?.messages ?? [];

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 space-y-2 overflow-y-auto p-4">
        {isLoading ? (
          <div className="space-y-2" data-testid="ig-dm-thread-loading">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-2/3 rounded-md" />
            ))}
          </div>
        ) : isError ? (
          <div
            className="flex items-center gap-2 text-sm text-destructive"
            data-testid="ig-dm-thread-error"
          >
            <CircleAlert className="h-4 w-4 shrink-0" /> Erro ao carregar mensagens.
          </div>
        ) : messages.length === 0 ? (
          <div
            className="text-center text-sm text-muted-foreground"
            data-testid="ig-dm-thread-empty"
          >
            Nenhuma mensagem ainda.
          </div>
        ) : (
          <div data-testid="ig-dm-thread">
            {messages.map((m) => (
              <div
                key={m.id}
                className={`mb-2 max-w-[75%] rounded-lg px-3 py-2 text-sm ${
                  m.direction === "outbound"
                    ? "ml-auto bg-primary text-primary-foreground"
                    : "bg-muted"
                }`}
              >
                {m.text}
              </div>
            ))}
          </div>
        )}
      </div>

      {gate && <div className="px-4 pb-2"><AppReviewNotice error={gate.error} /></div>}

      <form
        className="flex gap-2 border-t p-3"
        data-testid="ig-dm-send-form"
        onSubmit={(e) => {
          e.preventDefault();
          if (!text.trim() || !recipientId) return;
          send.mutate(
            { recipient_id: recipientId, text },
            { onSuccess: (res) => !isAppReviewGate(res) && setText("") },
          );
        }}
      >
        <Input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Escreva uma mensagem..."
          data-testid="ig-dm-send-input"
          disabled={!recipientId}
        />
        <Button
          type="submit"
          disabled={send.isPending || !recipientId}
          data-testid="ig-dm-send-submit"
        >
          {send.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </Button>
      </form>
    </div>
  );
}

export default function IgDMs() {
  const accountId = useActiveMetaAccountId();
  const { data } = useIgConversations(accountId);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  if (!accountId) {
    return (
      <Card>
        <CardContent
          className="p-6 text-center text-sm text-muted-foreground"
          data-testid="ig-dm-no-account"
        >
          Selecione uma conta conectada acima para ver as mensagens diretas.
        </CardContent>
      </Card>
    );
  }

  const selected = data?.conversations.find((c) => c.id === selectedId) ?? null;

  return (
    <Card className="overflow-hidden">
      <div className="grid h-[520px] grid-cols-1 sm:grid-cols-[280px_1fr]">
        <div className="border-b sm:border-b-0 sm:border-r">
          <ConversationList
            accountId={accountId}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
        </div>
        <div>
          {selectedId ? (
            <MessageThread
              accountId={accountId}
              conversationId={selectedId}
              recipientId={selected?.participant_id ?? null}
            />
          ) : (
            <div
              className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-sm text-muted-foreground"
              data-testid="ig-dm-no-selection"
            >
              <MessageCircle className="h-8 w-8 opacity-40" />
              Selecione uma conversa para ver as mensagens.
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}
