/**
 * JuliaChatWindow — thin adapter wiring `/api/conversations` onto the seed
 * `<ChatWindow>` organ (`@noctusai/lib/design-system`) via the shared
 * `<AgentChatWindow>` pass-through (`@/components/AgentChatWindow.tsx`,
 * extracted for Agent Studio's Conversar tab — contract §G, see that
 * file's header). All 2-pane rendering (thread list / thread panel /
 * composer / skeletons / empty / error / tool chips / approval cards)
 * lives in the organ; this file only supplies the adapter
 * (`useJuliaChat.ts`) and the "Nova conversa" action, mirroring
 * `products/social-wiring/frontend/src/components/WhatsAppChatWindow.tsx`.
 */
import { useMemo } from "react";
import { AgentChatWindow } from "@/components/AgentChatWindow";
import { buildJuliaChatAdapter } from "@/hooks/useJuliaChat";

export interface JuliaChatWindowProps {
  className?: string;
}

export function JuliaChatWindow({ className }: JuliaChatWindowProps) {
  // Stable identity across renders — ChatWindow calls each adapter hook by
  // reference every render; rebuilding this object would not itself break
  // anything (the hooks are plain functions, not memoized closures), but a
  // stable reference matches the established WhatsApp/`useMemo` convention.
  const adapter = useMemo(() => buildJuliaChatAdapter(), []);

  return (
    <AgentChatWindow
      scopeId="julia"
      adapter={adapter}
      emptyThreadsLabel="Nenhuma conversa ainda. Clique em “Nova conversa” para começar."
      emptySelectionLabel="Selecione uma conversa"
      className={className}
    />
  );
}

export default JuliaChatWindow;
