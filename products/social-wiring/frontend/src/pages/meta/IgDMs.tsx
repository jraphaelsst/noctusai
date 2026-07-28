/**
 * IgDMs — Instagram "DMs" subtab: a 2-pane chat surface (conversations list /
 * message thread + send) built on the shared seed `<ChatWindow>` organ
 * (`@noctusai/lib/design-system`) — the Wave 4 extraction referenced in the
 * pre-extraction version of this file. `WhatsAppChatWindow.tsx` is the
 * sibling consumer; a 3rd chat surface only needs an adapter, never a
 * ChatWindow change.
 *
 * This file's only job is normalizing the Wave 3 Meta DM DTOs
 * (`IGConversation`, `IGMessage` from `hooks/useMeta`) into ChatWindow's
 * generic `ChatThread` / `ChatMessage` shape, and wiring send.
 *
 * Sending requires a `recipient_id` per the Wave 3 contract body shape
 * (`{recipient_id, text}`) — resolved from the selected conversation's
 * `participant_id` inside the send adapter. No auto-reply toggle: the
 * Wave 3 contract has no AI-reply control for Instagram DMs (adapter omits
 * `useAutoReply` entirely — ChatWindow hides the control by construction).
 *
 * App Review gate: any write MAY come back as `{requires_app_review: true,
 * error}` (a 200, never thrown). The send adapter turns that into a thrown
 * `Error` so ChatWindow's composer surfaces the gate as an inline banner —
 * never a fake success.
 */
import { Card, CardContent } from "@/components/ui/card";
import { ChatWindow, type ChatWindowAdapter } from "@noctusai/lib/design-system";

import {
  isAppReviewGate,
  isMetaSetupGate,
  useActiveMetaAccountId,
  useIgConversations,
  useIgMessages,
  useSendIgMessage,
} from "@/hooks/useMeta";
import { AppReviewNotice } from "./AppReviewNotice";
import { MetaSetupNotice } from "./MetaSetupNotice";

// ─── Meta DM adapter ──────────────────────────────────────────────────────────

function useMetaDMThreadsAdapter(accountId: string | null) {
  const { data, isLoading, isError } = useIgConversations(accountId);
  // A setup gate carries no `conversations` — the main component renders
  // the actionable notice instead, so here it degrades to an empty list.
  const conversations = isMetaSetupGate(data) ? [] : data?.conversations ?? [];
  return {
    data: conversations.map((c) => ({
      id: c.id,
      title: c.participant_name ?? "Contato",
      lastMessagePreview: c.snippet,
      lastMessageAt: c.updated_time,
      unreadCount: c.unread_count,
    })),
    isLoading,
    isError,
  };
}

function useMetaDMMessagesAdapter(accountId: string | null, conversationId: string | null) {
  const { data, isLoading, isError } = useIgMessages(accountId, conversationId);
  const messages = isMetaSetupGate(data) ? [] : data?.messages ?? [];
  return {
    data: messages.map((m) => ({
      id: m.id,
      direction: m.direction,
      body: m.text,
      created_at: m.created_at,
    })),
    isLoading,
    isError,
  };
}

function useMetaDMSendAdapter(accountId: string | null, conversationId: string | null) {
  // Shares the TanStack Query cache entry with useMetaDMThreadsAdapter
  // (same queryKey) — no extra network call, just a lookup for participant_id.
  const { data } = useIgConversations(accountId);
  const conversations = isMetaSetupGate(data) ? [] : data?.conversations ?? [];
  const recipientId =
    conversations.find((c) => c.id === conversationId)?.participant_id ?? null;
  const send = useSendIgMessage(accountId, conversationId);

  return {
    isPending: send.isPending,
    mutateAsync: async ({ text }: { text: string }) => {
      if (!recipientId) {
        throw new Error("Não foi possível identificar o destinatário desta conversa.");
      }
      const result = await send.mutateAsync({ recipient_id: recipientId, text });
      if (isAppReviewGate(result)) {
        throw new Error(
          result.error ?? "Requer Revisão do app Meta (App Review) para enviar mensagens diretas.",
        );
      }
      return result;
    },
  };
}

const metaDMAdapter: ChatWindowAdapter = {
  useThreads: useMetaDMThreadsAdapter,
  useMessages: useMetaDMMessagesAdapter,
  useSend: useMetaDMSendAdapter,
};

// ─── Main component ───────────────────────────────────────────────────────────

export default function IgDMs() {
  const accountId = useActiveMetaAccountId();
  // Shares the TanStack cache entry with the ChatWindow adapters (same
  // queryKey) — no extra request. Intercepts the "needs Meta setup" gate
  // (Graph #3) so the tab shows an actionable card instead of an empty
  // ChatWindow that would misread as "no conversations".
  const { data: conversationsData } = useIgConversations(accountId);

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

  if (isMetaSetupGate(conversationsData)) {
    return <MetaSetupNotice error={conversationsData.error} />;
  }

  // Advanced-Access gate: the conversations edge structurally times out on an
  // account whose `instagram_manage_messages` is still Standard Access (the
  // backend maps that to `requires_app_review` rather than hanging). Render
  // the App-Review notice with Meta's actionable remedy instead of an
  // infinite ChatWindow skeleton that would misread as "no conversations".
  if (isAppReviewGate(conversationsData)) {
    return <AppReviewNotice error={conversationsData.error} />;
  }

  return (
    <Card className="overflow-hidden">
      <div className="h-[520px]">
        <ChatWindow
          scopeId={accountId}
          adapter={metaDMAdapter}
          emptyThreadsLabel="Nenhuma conversa por enquanto."
          emptySelectionLabel="Selecione uma conversa para ver as mensagens."
        />
      </div>
    </Card>
  );
}
