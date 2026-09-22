/**
 * CardHubButton — the shadcn-shape button SW's card hub is drawn with.
 *
 * Design-system copy of `products/social-wiring/frontend/src/components/ui/
 * button.tsx`: identical class strings per variant/size, so the seed card hub
 * (`components/card-hub/`) is pixel-identical to SW's card at desktop
 * (`project-history/roadmaps/cardhub-igig-crm-2026-09.wave-a-design.md`
 * Slice C). A sibling of — not a replacement for — the design-system `Button`
 * (`./Button.tsx`), whose variant vocabulary (`primary`/`md`) and sizing differ;
 * aliased `CardHub*` for the same collision reason as `CardHubSelect`.
 *
 * `class-variance-authority` is NOT pulled in: `cva` with no compound
 * variants is `cn(base, variant, size, className)`, and `cn` already runs
 * `tailwind-merge` — the same resolution cva's output gets in SW.
 */
import * as React from "react";
import { Slot } from "@radix-ui/react-slot";

import { cn } from "../../utils";

export type CardHubButtonVariant =
  | "default"
  | "destructive"
  | "outline"
  | "secondary"
  | "ghost"
  | "link";
export type CardHubButtonSize = "default" | "sm" | "lg" | "icon";

const BASE =
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0";

const VARIANT: Record<CardHubButtonVariant, string> = {
  default: "bg-primary text-primary-foreground hover:bg-primary/90",
  destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/90",
  outline: "border border-input bg-background hover:bg-accent hover:text-accent-foreground",
  secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
  ghost: "hover:bg-accent hover:text-accent-foreground",
  link: "text-primary underline-offset-4 hover:underline",
};

const SIZE: Record<CardHubButtonSize, string> = {
  default: "h-10 px-4 py-2",
  sm: "h-9 rounded-md px-3",
  lg: "h-11 rounded-md px-8",
  icon: "h-10 w-10",
};

/** The class string for a variant/size pair — `buttonVariants` in SW. */
export function cardHubButtonVariants({
  variant,
  size,
  className,
}: {
  variant?: CardHubButtonVariant | null;
  size?: CardHubButtonSize | null;
  className?: string;
} = {}): string {
  return cn(BASE, VARIANT[variant ?? "default"], SIZE[size ?? "default"], className);
}

export interface CardHubButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: CardHubButtonVariant | null;
  size?: CardHubButtonSize | null;
  asChild?: boolean;
}

export const CardHubButton = React.forwardRef<HTMLButtonElement, CardHubButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp className={cardHubButtonVariants({ variant, size, className })} ref={ref} {...props} />
    );
  },
);
CardHubButton.displayName = "CardHubButton";
