/**
 * AgentChatWindow — thin, provider-agnostic pass-through onto the seed
 * `<ChatWindow>` organ (`@noctusai/lib/design-system`), extracted per
 * Agent Studio CONTRACT.md §G "Conversar" ("reuse the seed ChatWindow organ
 * exactly the way Julia does ... extract a shared AgentChatWindow if it
 * removes duplication, WITHOUT changing Julia's behaviour").
 *
 * The only "duplication" between `JuliaChatWindow` and the Agent Studio
 * Chat tab was the `useMemo(() => buildXChatAdapter(), [])` + `<ChatWindow
 * .../>` wrapping shape — this file is that shared shape, adapter-blind
 * (it never imports `useJuliaChat` or `useStudioChat`). `JuliaChatWindow`
 * now renders through it with byte-identical props to before this slice
 * (verified: no test imports `JuliaChatWindow` directly, and this file
 * forwards every prop unchanged to `<ChatWindow>` — no new markup, no
 * behavioural seam).
 */
import { ChatWindow, type ChatWindowAdapter } from "@noctusai/lib/design-system";

export interface AgentChatWindowProps {
  /** Provider-scoped id (Julia's fixed "julia", or a studio agent's `key`). */
  scopeId: string | null;
  adapter: ChatWindowAdapter;
  emptyThreadsLabel?: string;
  emptySelectionLabel?: string;
  className?: string;
}

export function AgentChatWindow({
  scopeId,
  adapter,
  emptyThreadsLabel,
  emptySelectionLabel,
  className,
}: AgentChatWindowProps) {
  return (
    <ChatWindow
      scopeId={scopeId}
      adapter={adapter}
      emptyThreadsLabel={emptyThreadsLabel}
      emptySelectionLabel={emptySelectionLabel}
      className={className}
    />
  );
}

export default AgentChatWindow;
