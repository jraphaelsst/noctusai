/**
 * Progress — Radix-backed progress-bar primitive.
 *
 * Design-system copy of SW's local shadcn wrapper
 * (`products/social-wiring/frontend/src/components/ui/progress.tsx`) —
 * markup/classes/data-attributes kept byte-for-byte so SW's card-hub
 * (checklist completion bar) can swap onto this import with zero visual
 * change at desktop
 * (`project-history/roadmaps/cardhub-igig-crm-2026-09.wave-a-design.md`
 * Slice B). Non-interactive — no touch-target concern.
 */
import * as React from "react";
import * as ProgressPrimitive from "@radix-ui/react-progress";

import { cn } from "../../utils";

interface ProgressProps extends React.ComponentPropsWithoutRef<typeof ProgressPrimitive.Root> {
  indicatorClassName?: string;
}

const Progress = React.forwardRef<React.ElementRef<typeof ProgressPrimitive.Root>, ProgressProps>(
  ({ className, value, indicatorClassName, ...props }, ref) => (
    <ProgressPrimitive.Root
      ref={ref}
      className={cn("relative h-2 w-full overflow-hidden rounded-full bg-secondary/20", className)}
      {...props}
    >
      <ProgressPrimitive.Indicator
        className={cn("h-full w-full flex-1 bg-primary transition-all", indicatorClassName)}
        style={{ transform: `translateX(-${100 - (value || 0)}%)` }}
      />
    </ProgressPrimitive.Root>
  ),
);
Progress.displayName = ProgressPrimitive.Root.displayName;

export { Progress };
