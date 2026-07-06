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
  useActiveMetaAccountId,
  useIgConversations,
  useIgMessages,
  useSendIgMessage,
} from "@/hooks/useMeta";

// ─── Meta DM adapter ──────────────────────────────────────────────────────────

function useMetaDMThreadsAdapter(accountId: string | null) {
  const { data, isLoading, isError } = useIgConversations(accountId);
  return {
    data: (data?.conversations ?? []).map((c) => ({
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
  return {
    data: (data?.messages ?? []).map((m) => ({
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
  const recipientId =
    data?.conversations.find((c) => c.id === conversationId)?.participant_id ?? null;
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
