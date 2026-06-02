/**
 * Input — generic single-line text input primitive.
 *
 * Usage:
 *   <Input placeholder="Nome da conta" value={val} onChange={...} />
 *   <Input type="url" disabled={busy} />
 *
 * Styling follows the design-system token idiom:
 *   h-8, rounded-md, border-input, bg-background, ring on focus,
 *   placeholder:text-muted-foreground, disabled:opacity-50.
 *
 * Fully forwards the ref and all native <input> props.
 */
import * as React from "react";
import { cn } from "../../utils";

export interface InputProps
  extends React.InputHTMLAttributes<HTMLInputElement> {}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type = "text", ...props }, ref) => (
    <input
      ref={ref}
      type={type}
      className={cn(
        "h-8 w-full rounded-md border border-input bg-background px-2.5 text-sm",
        "ring-offset-background placeholder:text-muted-foreground",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";
