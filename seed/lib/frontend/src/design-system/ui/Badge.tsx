/**
 * Badge — generic pill-shaped status/label chip.
 *
 * Usage:
 *   <Badge variant="default">Validado</Badge>
 *   <Badge variant="destructive">Erro</Badge>
 *   <Badge variant="outline">Desconectado</Badge>
 *   <Badge variant="muted">Pendente</Badge>
 *   <Badge className="custom-class">Custom</Badge>
 *
 * Variants follow the design-system token naming convention
 * (primary / destructive / muted / outline — no per-component colours).
 */
import * as React from "react";
import { cn } from "../../utils";

export type BadgeVariant = "default" | "destructive" | "muted" | "outline";

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
}

const variantClass: Record<BadgeVariant, string> = {
  default:
    "border-transparent bg-primary text-primary-foreground",
  destructive:
    "border-transparent bg-destructive text-destructive-foreground",
  muted:
    "border-muted-foreground/30 bg-muted text-muted-foreground",
  outline:
    "border border-muted-foreground/40 bg-transparent text-muted-foreground",
};

export const Badge = React.forwardRef<HTMLSpanElement, BadgeProps>(
  ({ variant = "default", className, children, ...props }, ref) => (
    <span
      ref={ref}
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold",
        variantClass[variant],
        className,
      )}
      {...props}
    >
      {children}
    </span>
  ),
);
Badge.displayName = "Badge";
