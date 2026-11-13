/**
 * `/conversas` -- the owner's conversations on the personal line: read them and answer them (the seed `WhatsAppInbox`
 * organ over the first connected line). What the assistant sent shows in the thread like any other message from the
 * line; the owner's own replies (here or from the phone) are also handed to the assistant so it does not contradict them.
 *
 * Admin-only, like every route behind it (the server answers 403 to a member): this is the owner's personal line, with
 * third parties' messages. `?chat=<jid>` deep-links a conversation and the open chat is written back to the URL.
 */
import * as React from "react";
import { Link, useSearchParams } from "react-router-dom";
import { MessageCircle } from "lucide-react";
import { WhatsAppInbox } from "@noctusai/lib/components";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";

import { connectionsHooks, inboxHooks } from "@/lib/whatsapp";

export const CONEXAO_PATH = "/conexao";

export default function Conversas() {
  const isAdmin = useIsOrgAdmin();
  const [params, setParams] = useSearchParams();
  const { data: connections, showSkeleton, error, refetch } = connectionsHooks.useConnections();
  const connectionId = connections?.[0]?.id ?? null;

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

  if (!isAdmin) {
    return (
      <div className="rounded-lg border border-border bg-card p-4 text-sm text-muted-foreground" data-testid="conversas-acesso-restrito">
        Esta página é restrita a administradores.
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="conversas-page">
      <div className="flex items-center gap-3">
        <MessageCircle className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold text-foreground">Conversas</h1>
          <p className="text-sm text-muted-foreground">As conversas da sua linha: leia e responda por aqui.</p>
        </div>
      </div>

      {showSkeleton ? (
        <div className="h-64 animate-pulse rounded-lg border border-border bg-muted/40" data-testid="conversas-loading" />
      ) : error && !connections ? (
        <div className="rounded-lg border border-destructive/40 p-4 text-sm" role="alert" data-testid="conversas-erro">
          Não foi possível carregar a linha de WhatsApp.{" "}
          <button type="button" className="underline" onClick={() => void refetch()}>Tentar de novo</button>
        </div>
      ) : !connectionId ? (
        <div className="rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground" data-testid="conversas-sem-conexao">
          Nenhum WhatsApp conectado ainda. <Link className="underline" to={CONEXAO_PATH}>Conectar o número</Link> para ver as conversas aqui.
        </div>
      ) : (
        <WhatsAppInbox
          hooks={inboxHooks}
          connectionId={connectionId}
          enableAgentPause
          allowDeleteChat
          initialChatId={params.get("chat")}
          onSelectChat={onSelectChat}
        />
      )}
    </div>
  );
}
