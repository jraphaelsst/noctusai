/**
 * `/conversas` -- the seed WhatsApp inbox (read + reply) over the first connected line.
 *
 * `?chat=<jid>` deep-links a conversation (the lead modal's "abrir conversa"); the open chat is written back to
 * the URL so a reload or a shared link lands on the same conversation. The chat header carries "Ver lead": it
 * opens the same lead modal as the funnel when the number has a lead (a deleted lead simply has no button).
 */
import * as React from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { MessageCircle, UserRound } from "lucide-react";
import { LeadDetailModal, type InboxChat } from "@noctusai/lib";
import { WhatsAppInbox } from "@noctusai/lib/components";
import { Button } from "@noctusai/lib/design-system";

import { CONEXOES_PATH, connectionsHooks, conversationPath, inboxHooks, leadsHooks } from "@/lib/crm";

/** The lead of an open chat, found by the number (or the name when WhatsApp hides it), matched on the chat id. */
function VerLead({ chat }: { chat: InboxChat }) {
  const [open, setOpen] = React.useState(false);
  const navigate = useNavigate();
  const list = leadsHooks.useLeadsList({ q: chat.phone ?? chat.name }, 20);
  const lead = (list.data ?? []).find((l) => l.whatsapp_chat_id === chat.chat_id) ?? null;
  if (!lead) return null;
  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)} data-testid="conversa-ver-lead">
        <UserRound className="mr-1 h-4 w-4" />
        Ver lead
      </Button>
      <LeadDetailModal
        hooks={leadsHooks}
        lead={open ? lead : null}
        onClose={() => setOpen(false)}
        onOpenConversation={(l) => l.whatsapp_chat_id && navigate(conversationPath(l.whatsapp_chat_id))}
      />
    </>
  );
}

export default function Conversas() {
  const [params, setParams] = useSearchParams();
  const { data: connections, showSkeleton, error, refetch } = connectionsHooks.useConnections();
  const [picked, setPicked] = React.useState<string | null>(null);
  const connectionId = picked ?? connections?.[0]?.id ?? null;

  const onSelectChat = React.useCallback(
    (chatId: string | null) => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (chatId) next.set("chat", chatId);
          else next.delete("chat");
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  return (
    <div className="space-y-4" data-testid="conversas-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <MessageCircle className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-2xl font-bold text-foreground">Conversas</h1>
            <p className="text-sm text-muted-foreground">As conversas de WhatsApp com quem te procura.</p>
          </div>
        </div>
        {(connections?.length ?? 0) > 1 && (
          <select
            aria-label="Linha de WhatsApp"
            className="h-9 rounded-md border border-input bg-background px-2 text-sm"
            value={connectionId ?? ""}
            onChange={(e) => setPicked(e.target.value)}
          >
            {connections!.map((c) => (
              <option key={c.id} value={c.id}>{c.label}</option>
            ))}
          </select>
        )}
      </div>

      {showSkeleton ? (
        <div className="h-64 animate-pulse rounded-lg border border-border bg-muted/40" data-testid="conversas-loading" />
      ) : error && !connections ? (
        <div className="rounded-lg border border-destructive/40 p-4 text-sm" role="alert">
          Não foi possível carregar as linhas de WhatsApp.{" "}
          <button type="button" className="underline" onClick={() => void refetch()}>Tentar de novo</button>
        </div>
      ) : !connectionId ? (
        <div className="rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground" data-testid="conversas-sem-conexao">
          Nenhum WhatsApp conectado ainda. <Link className="underline" to={CONEXOES_PATH}>Conectar um número</Link> para ver as conversas aqui.
        </div>
      ) : (
        <WhatsAppInbox
          hooks={inboxHooks}
          connectionId={connectionId}
          initialChatId={params.get("chat")}
          onSelectChat={onSelectChat}
          renderChatHeaderExtra={(chat) => <VerLead chat={chat} />}
        />
      )}
    </div>
  );
}
