/**
 * Checkbox — Radix-backed checkbox primitive.
 *
 * Design-system copy of SW's local shadcn wrapper
 * (`products/social-wiring/frontend/src/components/ui/checkbox.tsx`) —
 * markup/classes/data-attributes kept byte-for-byte so SW's card-hub
 * (`TokenCheckbox`, checklist items) can swap onto this import with zero
 * visual change at desktop
 * (`project-history/roadmaps/cardhub-igig-crm-2026-09.wave-a-design.md`
 * Slice B).
 *
 * Mobile-first touch target (R0): the visual box stays `h-4 w-4` (16px) at
 * every breakpoint — unchanged from SW's copy — but a `::after` hit-area is
 * extended by 12px on each side below the `sm` (640px) breakpoint so the
 * tappable region reaches the 40px floor on phones. `sm:after:inset-0`
 * collapses the extension back to the visible box at desktop, so desktop
 * sizing (visual AND hit-area) is byte-identical to SW's original.
 */
import * as React from "react";
import * as CheckboxPrimitive from "@radix-ui/react-checkbox";
import { Check } from "lucide-react";

import { cn } from "../../utils";

const Checkbox = React.forwardRef<
  React.ElementRef<typeof CheckboxPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof CheckboxPrimitive.Root>
>(({ className, ...props }, ref) => (
  <CheckboxPrimitive.Root
    ref={ref}
    className={cn(
      "peer relative h-4 w-4 shrink-0 rounded-sm border border-primary ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 data-[state=checked]:bg-primary data-[state=checked]:text-primary-foreground",
      "after:absolute after:-inset-3 after:content-[''] sm:after:inset-0",
      className,
    )}
    {...props}
  >
    <CheckboxPrimitive.Indicator className={cn("flex items-center justify-center text-current")}>
      <Check className="h-3 w-3" />
    </CheckboxPrimitive.Indicator>
  </CheckboxPrimitive.Root>
));
Checkbox.displayName = CheckboxPrimitive.Root.displayName;

export { Checkbox };
