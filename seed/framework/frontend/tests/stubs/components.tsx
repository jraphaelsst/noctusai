/**
 * Test-time stub for `@noctusai/lib/components`.
 *
 * `layout.tsx` imports `HelpChatBubble` from here (the `helpChat` layout
 * option, 2026-09-28). The REAL component pulls `react-markdown` +
 * `remark-gfm` + `rehype-slug` (for rendering streamed assistant replies) —
 * not installed in this package for the same reason `design-system.tsx`
 * stubs the Radix/lucide surface: this harness tests FRAMEWORK wiring, not
 * organ internals (those are `seed/lib/frontend`'s own test suite —
 * `HelpChatBubble.test.tsx`).
 */
import React from "react";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const HelpChatBubble: React.FC<any> = ({ title, endpoint, starters }) => (
  <div data-testid="help-chat-bubble-stub">
    <span data-testid="help-chat-title">{title}</span>
    <span data-testid="help-chat-endpoint">{endpoint ?? ""}</span>
    <span data-testid="help-chat-starters-count">{starters?.length ?? 0}</span>
  </div>
);
