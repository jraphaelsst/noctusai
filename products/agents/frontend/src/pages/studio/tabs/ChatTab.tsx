/**
 * Conversar tab — Agent Studio CONTRACT.md §G "Conversar" (`/studio/:key?tab=conversar`).
 *
 * Reuses the seed `<ChatWindow>` organ exactly like Julia does, through the
 * shared `<AgentChatWindow>` pass-through (`@/components/AgentChatWindow.tsx`).
 * All 2-pane rendering (loading/empty/error/success, both panes) lives in
 * the organ; this tab only owns the "Nova conversa" action + the optional
 * client selector shown at conversation creation (contract §D6 —
 * `client_id` is pinned once, at creation, never changed on an existing
 * conversation). Each assistant message's "versão N · prompt sha256:…"
 * link (contract §G) is built into the adapter itself
 * (`useStudioChat.ts`'s `toChatMessage`), not this page.
 */
import { useMemo, useState } from "react";
import { MessageCircle, Plus } from "lucide-react";
import { toast } from "sonner";
import { Button, Select } from "@noctusai/lib/design-system";
import { AgentChatWindow } from "@/components/AgentChatWindow";
import { buildStudioChatAdapter, useCreateStudioConversation } from "@/hooks/studio/useStudioChat";
import { useClients } from "@/hooks/studio/useClients";
import { errorMessage } from "@/lib/errors";

export default function ChatTab({ agentKey }: { agentKey: string }) {
  const adapter = useMemo(() => buildStudioChatAdapter(agentKey), [agentKey]);
  const { data: clients } = useClients(agentKey);
  const activeClients = useMemo(() => (clients ?? []).filter((c) => c.ativo), [clients]);
  const [clientId, setClientId] = useState<string>("");
  const createConversation = useCreateStudioConversation(agentKey);
  const [creating, setCreating] = useState(false);

  async function handleNewConversation() {
    setCreating(true);
    try {
      await createConversation.mutateAsync(clientId ? { clientId } : undefined);
      toast.success("Conversa criada — selecione-a na lista à esquerda.");
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="flex h-[calc(100vh-14rem)] flex-col space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <MessageCircle className="h-5 w-5 text-primary" />
          <div>
            <h2 className="text-lg font-semibold text-foreground">Conversar</h2>
            <p className="text-xs text-muted-foreground">Converse com o agente para testar a versão ativa.</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {activeClients.length > 0 && (
            <Select
              value={clientId}
              onChange={(e) => setClientId(e.target.value)}
              className="w-48"
              aria-label="Cliente em foco (opcional)"
              data-testid="chat-tab-client-select"
            >
              <option value="">Sem cliente</option>
              {activeClients.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.nome}
                </option>
              ))}
            </Select>
          )}
          <Button variant="primary" onClick={handleNewConversation} disabled={creating} data-testid="studio-chat-new-conversation">
            <Plus className="mr-1.5 h-4 w-4" />
            Nova conversa
          </Button>
        </div>
      </div>

      <div className="min-h-0 flex-1 rounded-lg border border-border bg-card">
        <AgentChatWindow
          scopeId={agentKey}
          adapter={adapter}
          emptyThreadsLabel="Nenhuma conversa ainda. Clique em “Nova conversa” para começar."
          emptySelectionLabel="Selecione uma conversa"
          className="h-full"
        />
      </div>
    </div>
  );
}
