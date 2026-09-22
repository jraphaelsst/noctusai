/**
 * Textarea (Radix-shape sibling) — plain-HTML textarea wrapper matching
 * SW's local shadcn copy exactly
 * (`products/social-wiring/frontend/src/components/ui/textarea.tsx`).
 *
 * The design-system already ships a `Textarea` (see `FormControls.tsx` —
 * `rows=4` default, `monospace` variant, used by academia/agents/community
 * pages today). SW's copy is near-identical but not byte-identical
 * (`min-h-[80px]`/`text-base md:text-sm` vs. `rows=4`/`text-sm`), and
 * changing the existing shared export's classes would be a visual
 * regression for its current consumers. This file is the card-hub-flavored
 * twin, kept name-identical to SW's own `Textarea` internally (so a diff
 * against SW's copy stays trivial) and re-exported as `CardHubTextarea`
 * from the barrel to avoid the name collision
 * (`project-history/roadmaps/cardhub-igig-crm-2026-09.wave-a-design.md`
 * Slice B risk: "Visual drift from seed primitives replacing SW shadcn
 * copies — keep markup/test ids").
 */
import * as React from "react";

import { cn } from "../../utils";

const Textarea = React.forwardRef<HTMLTextAreaElement, React.ComponentProps<"textarea">>(
  ({ className, ...props }, ref) => {
    return (
      <textarea
        className={cn(
          "flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-base ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 md:text-sm",
          className,
        )}
        ref={ref}
        {...props}
      />
    );
  },
);
Textarea.displayName = "Textarea";

export { Textarea };
