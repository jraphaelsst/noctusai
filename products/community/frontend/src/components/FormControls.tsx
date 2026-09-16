/**
 * Small local form/layout primitives that `@noctusai/lib/design-system`
 * does not ship yet (Textarea, Select, Checkbox, Card, Field, EmptyState,
 * ErrorState). Styled with the exact token idiom the seed
 * `Input`/`Button`/`Badge` primitives use (see
 * `seed/lib/frontend/src/design-system/ui/Input.tsx`) so a page mixing
 * these with seed primitives looks identical.
 *
 * Mirrors `products/academia-de-reciclagem/frontend/src/components/
 * FormControls.tsx` — the established house convention (kept product-local,
 * one file, deliberately small; promote to the seed the moment a second
 * *new* product needs the same shapes — this is already the second
 * consumer of this exact shape, so the DRY recurrence is now N=2, tracked
 * in this delivery's `drift-found:` footer rather than promoted mid-slice).
 */
import * as React from "react";
import { cn } from "@noctusai/lib";

export const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("rounded-lg border border-border bg-card p-4", className)} {...props} />
  ),
);
Card.displayName = "Card";

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {}

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, rows = 4, ...props }, ref) => (
    <textarea
      ref={ref}
      rows={rows}
      className={cn(
        "w-full rounded-md border border-input bg-background px-2.5 py-2 text-sm",
        "ring-offset-background placeholder:text-muted-foreground",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  ),
);
Textarea.displayName = "Textarea";

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {}

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

export interface CheckboxProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label: string;
}

export const Checkbox = React.forwardRef<HTMLInputElement, CheckboxProps>(
  ({ className, label, id, ...props }, ref) => (
    <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer" htmlFor={id}>
      <input
        ref={ref}
        id={id}
        type="checkbox"
        className={cn("rounded border-border", className)}
        {...props}
      />
      {label}
    </label>
  ),
);
Checkbox.displayName = "Checkbox";

export function Field({
  label,
  required,
  error,
  help,
  children,
}: {
  label: string;
  required?: boolean;
  error?: string | null;
  help?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block space-y-1">
      <span className="text-xs font-medium text-foreground">
        {label}
        {required ? <span className="text-destructive"> *</span> : null}
      </span>
      {children}
      {help ? <span className="block text-xs text-muted-foreground">{help}</span> : null}
      {error ? <span className="block text-xs text-destructive">{error}</span> : null}
    </label>
  );
}

/** Form-level error banner — the field-level 4xx message from the backend. */
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
