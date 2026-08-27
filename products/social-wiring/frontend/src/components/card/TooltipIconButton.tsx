/**
 * TooltipIconButton / TooltipCaption — the card's icon-only button contract.
 *
 * The card's buttons lost their visible text: at 90vw × 90vh the middle pane
 * carries a checklist, an extras listing, several collapsible panels and a
 * comment composer, and a row of word-buttons above each of them was more
 * chrome than content. The caption did NOT disappear — it moved onto hover.
 *
 * 🔴 A TOOLTIP IS NOT AN ACCESSIBLE NAME.
 * ---------------------------------------
 * Every button here carries `aria-label` with the SAME string the tooltip
 * shows. A hover-only caption is invisible to a screen reader and to anyone
 * driving with a keyboard, so the two are shipped together, by construction,
 * rather than left to each call site to remember. `TooltipIconButton` cannot
 * be constructed without a `label`, which is what makes that guarantee hold.
 *
 * 🔴 IT MOUNTS ITS OWN `TooltipProvider`.
 * ---------------------------------------
 * Radix's `Tooltip` throws without an ancestor provider, and nothing in this
 * product mounts one — the app shell does not, and `PortaisTable` worked
 * around the gap by falling back to a native `title` (see its docblock). A
 * provider is context only, so nesting one per button costs nothing at
 * runtime and makes this component renderable ANYWHERE, including in a test
 * that mounts a section on its own with no shell around it. That is the same
 * property everything under `card/**` already has, and the reason a shared
 * provider mounted "somewhere up there" would have been a trap.
 *
 * Presentational only, same contract as the rest of `card/**`.
 */
import { forwardRef } from "react";
import type { ComponentProps, ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

type Lado = "top" | "right" | "bottom" | "left";

export interface TooltipCaptionProps {
  /** The words the button used to show. Also its accessible name — the caller
   *  is responsible for putting the SAME string on the child's `aria-label`;
   *  `TooltipIconButton` below does it for you. */
  label: string;
  children: ReactNode;
  side?: Lado;
}

/**
 * Wraps any trigger — including a `PopoverTrigger` — in the hover caption.
 * Used where the button cannot be a plain `TooltipIconButton` because another
 * primitive already owns it.
 */
export function TooltipCaption({ label, children, side = "top" }: TooltipCaptionProps) {
  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>{children}</TooltipTrigger>
        <TooltipContent side={side}>{label}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

export interface TooltipIconButtonProps
  extends Omit<ComponentProps<typeof Button>, "children" | "aria-label"> {
  /** The caption. Rendered as the tooltip AND as the accessible name. */
  label: string;
  icon: LucideIcon;
  testId?: string;
  side?: Lado;
  iconClassName?: string;
}

export const TooltipIconButton = forwardRef<HTMLButtonElement, TooltipIconButtonProps>(
  function TooltipIconButton(
    {
      label,
      icon: Icon,
      testId,
      side = "top",
      className,
      iconClassName,
      variant = "ghost",
      size = "icon",
      ...rest
    },
    ref,
  ) {
    return (
      <TooltipCaption label={label} side={side}>
        <Button
          ref={ref}
          type="button"
          variant={variant}
          size={size}
          aria-label={label}
          data-testid={testId}
          className={cn("h-8 w-8 shrink-0", className)}
          {...rest}
        >
          <Icon className={cn("h-4 w-4", iconClassName)} aria-hidden="true" />
        </Button>
      </TooltipCaption>
    );
  },
);
