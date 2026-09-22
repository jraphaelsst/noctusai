/**
 * CardHubInput — the shadcn-shape text input SW's card hub is drawn with.
 *
 * Design-system copy of `products/social-wiring/frontend/src/components/ui/
 * input.tsx`, class string byte-for-byte (h-10, `md:text-sm`), so the seed card
 * hub is pixel-identical to SW's card at desktop
 * (`project-history/roadmaps/cardhub-igig-crm-2026-09.wave-a-design.md`
 * Slice C). The design-system `Input` (`./Input.tsx`) is a denser h-8 control;
 * aliased `CardHub*` for the same collision reason as `CardHubSelect`.
 */
import * as React from "react";

import { cn } from "../../utils";

export const CardHubInput = React.forwardRef<HTMLInputElement, React.ComponentProps<"input">>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-base ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 md:text-sm",
          className,
        )}
        ref={ref}
        {...props}
      />
    );
  },
);
CardHubInput.displayName = "CardHubInput";
