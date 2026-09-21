/**
 * Small local form/layout primitives that `@noctusai/lib/design-system`
 * does not ship yet (Textarea, Select, Card, Field, EmptyState, ErrorState).
 * Styled with the same token idiom as the seed `Input`/`Button`/`Badge`
 * primitives (`seed/lib/frontend/src/design-system/ui/Input.tsx`) and
 * mirrors `products/academia-de-reciclagem/frontend/src/components/FormControls.tsx`
 * byte-for-byte on the shapes shared with it — kept product-local per that
 * file's own note ("promote to the seed the moment a second product needs
 * the same shapes"); this is now N=2, flagged in the handback as a
 * scoped-improvement rather than promoted mid-slice.
 */
import * as React from "react";
import { cn } from "@noctusai/lib";

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  "data-testid"?: string;
}

export const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("rounded-lg border border-border bg-card p-4", className)} {...props} />
  ),
);
Card.displayName = "Card";

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  monospace?: boolean;
  "data-testid"?: string;
}

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, rows = 4, monospace, ...props }, ref) => (
    <textarea
      ref={ref}
      rows={rows}
      className={cn(
        "w-full rounded-md border border-input bg-background px-2.5 py-2 text-sm",
        "ring-offset-background placeholder:text-muted-foreground",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
        "disabled:cursor-not-allowed disabled:opacity-50",
        monospace && "font-mono text-xs",
        className,
      )}
      {...props}
    />
  ),
);
Textarea.displayName = "Textarea";

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  "data-testid"?: string;
}

export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, children, ...props }, ref) => (
    <select
      ref={ref}
      className={cn(
        "h-8 w-full rounded-md border border-input bg-background px-2.5 text-sm",
        "ring-offset-background",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    >
      {children}
    </select>
  ),
);
Select.displayName = "Select";

export function Field({
  label,
  required,
  error,
  children,
}: {
  label: string;
  required?: boolean;
  error?: string | null;
  children: React.ReactNode;
}) {
  return (
    <label className="block space-y-1">
      <span className="text-xs font-medium text-foreground">
        {label}
        {required ? <span className="text-destructive"> *</span> : null}
      </span>
      {children}
      {error ? <span className="block text-xs text-destructive">{error}</span> : null}
    </label>
  );
}

export function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
      {message}
    </div>
  );
}

export function EmptyState({ message }: { message: string }) {
  return <div className="py-12 text-center text-sm text-muted-foreground">{message}</div>;
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div role="alert" className="py-12 text-center text-sm text-destructive">
      {message}
    </div>
  );
}
