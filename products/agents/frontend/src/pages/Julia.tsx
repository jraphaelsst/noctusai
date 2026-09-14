/**
 * Julia chat page — contract §E.2/§E.3/§E.7 (`/julia`).
 *
 * All chat rendering + realtime (message streaming, tool chips, approval
 * cards, "Julia está pensando…") lives in the seed `<ChatWindow>` organ via
 * `<JuliaChatWindow>` (`@/components/JuliaChatWindow.tsx`); this page only
 * owns the "Nova conversa" action. Composer errors (409 `turn_in_progress` /
 * `agent_off`, 429 rate limit) surface INSIDE `ChatWindow`'s own inline
 * error banner — `useJuliaSendAdapter` (`@/hooks/useJuliaChat.ts`) throws a
 * PT-BR-mapped `Error` that the organ renders verbatim, never faked as a
 * success.
 *
 * `<ChatWindow>` has no external "select this thread" seam (its
 * `selectedThreadId` is fully internal state) — a newly created conversation
 * appears at the top of the thread list (sorted by recency in
 * `useThreads`), and the user opens it from there, rather than this page
 * reaching into the organ's internals to auto-select it.
 */
import { useState } from "react";
import { Plus, MessageCircle } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@noctusai/lib/design-system";
import { JuliaChatWindow } from "@/components/JuliaChatWindow";
import { useCreateConversation } from "@/hooks/useJuliaChat";
import { errorMessage } from "@/lib/errors";

export default function Julia() {
  const createConversation = useCreateConversation();
  const [creating, setCreating] = useState(false);

  async function handleNewConversation() {
    setCreating(true);
    try {
      await createConversation.mutateAsync();
      toast.success("Conversa criada — selecione-a na lista à esquerda.");
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <MessageCircle className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-2xl font-bold text-foreground">Julia</h1>
            <p className="text-sm text-muted-foreground">Converse com o agente Julia.</p>
          </div>
        </div>
        <Button
          variant="primary"
          onClick={handleNewConversation}
          disabled={creating}
          data-testid="julia-new-conversation"
        >
          <Plus className="mr-1.5 h-4 w-4" />
          Nova conversa
        </Button>
      </div>

      <div className="min-h-0 flex-1 rounded-lg border border-border bg-card">
        <JuliaChatWindow className="h-full" />
      </div>
    </div>
  );
}
