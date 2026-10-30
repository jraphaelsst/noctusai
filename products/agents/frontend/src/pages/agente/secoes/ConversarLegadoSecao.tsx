/**
 * "Conversar" section of a LEGACY chat agent's page (`/agentes/:key?tab=conversar`; `/bia` redirects here) —
 * contract §E.2/§E.3/§E.7. agents-unified CONTRACT §3: the server lists this section only on a legacy
 * `claude_sdk` agent; an org Studio agent's "Conversar" is the Studio chat tab instead.
 *
 * All chat rendering + realtime (message streaming, tool chips, approval
 * cards, "Bia está pensando…") lives in the seed `<ChatWindow>` organ via
 * `<LegacyChatWindow>` (`@/components/LegacyChatWindow.tsx`); this page owns
 * the "Nova conversa" action AND (2026-09-22) the selected conversation id,
 * via `ChatWindow`'s new controlled-selection seam
 * (`selectedThreadId`/`onSelectThread`) — a prod click-through found "Nova
 * conversa" creating a conversation the right pane never opened (still
 * showing "Selecione uma conversa"), so a double click silently left two
 * empty conversations behind. Selecting the new id here the moment it comes
 * back closes that gap; `ChatWindow` still owns in-list navigation and
 * reports every user click back up via `onSelectThread`, so the two stay in
 * sync either direction. Composer errors (409 `turn_in_progress` /
 * `agent_off`, 429 rate limit) surface INSIDE `ChatWindow`'s own inline
 * error banner — `useLegacySendAdapter` (`@/hooks/useLegacyChat.ts`) throws a
 * PT-BR-mapped `Error` that the organ renders verbatim, never faked as a
 * success.
 *
 * Duplicate-empty-conversation guard: deliberately NOT added. Detecting
 * "the selected conversation is empty and unsent" from this page would mean
 * mounting a second `useLegacyMessagesAdapter(selectedConversationId)` call
 * here — which opens a SECOND SSE connection to the same conversation
 * stream (the hook's realtime subscription is not separable from its
 * message query) purely to answer a yes/no question `ChatWindow` already
 * has the answer to internally. Not simple, and a second live stream per
 * page is a surprise of its own — out of scope for this pass.
 */
import { useState } from "react";
import { Plus } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@noctusai/lib/design-system";
import { LegacyChatWindow } from "@/components/LegacyChatWindow";
import { useCreateConversation } from "@/hooks/useLegacyChat";
import { errorMessage } from "@/lib/errors";
import type { SecaoProps } from "../secaoTypes";

export default function ConversarLegadoSecao({ agente }: SecaoProps) {
  const createConversation = useCreateConversation();
  const [creating, setCreating] = useState(false);
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);

  async function handleNewConversation() {
    setCreating(true);
    try {
      const conversation = await createConversation.mutateAsync();
      setSelectedConversationId(conversation.id);
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="flex h-[calc(100vh-14rem)] flex-col space-y-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">Converse com {agente.nome}.</p>
        <Button
          variant="primary"
          onClick={handleNewConversation}
          disabled={creating}
          data-testid="conversar-nova-conversa"
        >
          <Plus className="mr-1.5 h-4 w-4" />
          Nova conversa
        </Button>
      </div>

      <div className="min-h-0 flex-1 rounded-lg border border-border bg-card">
        <LegacyChatWindow
          className="h-full"
          selectedThreadId={selectedConversationId}
          onSelectThread={setSelectedConversationId}
        />
      </div>
    </div>
  );
}
