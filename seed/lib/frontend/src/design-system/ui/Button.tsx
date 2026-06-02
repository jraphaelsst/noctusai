/**
 * Button — generic button primitive with three variants and two sizes.
 *
 * Usage:
 *   <Button variant="primary">Salvar</Button>
 *   <Button variant="outline">Cancelar</Button>
 *   <Button variant="ghost" size="icon" aria-label="Fechar">
 *     <X className="h-4 w-4" />
 *   </Button>
 *
 * Variants:
 *   primary — filled, bg-primary / text-primary-foreground
 *   outline — bordered, bg-background
 *   ghost   — no background, hover:bg-accent (icon buttons)
 *
 * Sizes:
 *   sm   — h-7 px-3 text-xs  (compact inline controls)
 *   md   — h-8 px-4 text-sm  (default)
 *   icon — h-7 w-7 (square icon-only button, no px override)
 */
import * as React from "react";
import { cn } from "../../utils";

export type ButtonVariant = "primary" | "outline" | "ghost";
export type ButtonSize = "sm" | "md" | "icon";

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

const variantClass: Record<ButtonVariant, string> = {
  primary:
    "bg-primary text-primary-foreground hover:bg-primary/90",
  outline:
    "border border-input bg-background hover:bg-accent",
  ghost:
    "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
};

const sizeClass: Record<ButtonSize, string> = {
  sm: "h-7 px-3 text-xs",
  md: "h-8 px-4 text-sm",
  icon: "h-7 w-7",
};

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      variant = "outline",
      size = "md",
      className,
      disabled,
      children,
      ...props
    },
    ref,
  ) => (
    <button
      ref={ref}
      type="button"
      disabled={disabled}
      className={cn(
        "inline-flex items-center justify-center gap-1 rounded-md font-medium transition-colors",
        "disabled:pointer-events-none disabled:opacity-50",
        variantClass[variant],
        sizeClass[size],
        className,
      )}
      {...props}
    >
      {children}
    </button>
  ),
);
Button.displayName = "Button";
