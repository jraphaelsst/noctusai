/**
 * Small local form/layout primitives that `@noctusai/lib/design-system`
 * does not ship yet (Textarea, Select, Card, Field). Styled with the exact
 * token idiom the seed `Input`/`Button`/`Badge` primitives use (see
 * `seed/lib/frontend/src/design-system/ui/Input.tsx`) so a page mixing
 * these with seed primitives looks identical. Kept in ONE file, product-
 * local, deliberately small — promote to the seed the moment a second
 * product needs the same shapes (DRY N=2 triage).
 */
import * as React from "react";
import { cn } from "@noctusai/lib";

export const Card = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("rounded-lg border border-border bg-card p-4", className)}
    {...props}
  />
));
Card.displayName = "Card";

export interface TextareaProps
  extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {}

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

export interface SelectProps
  extends React.SelectHTMLAttributes<HTMLSelectElement> {}

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

/** Form-level error banner — the field-level 422 message from the backend. */
export function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div
      role="alert"
      className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive"
    >
      {message}
    </div>
  );
}

/** Inline safe markdown block — no HTML injection, no markdown lib dep.
 * Mirrors `products/knowledge-extractor/frontend/src/pages/LessonViewer.tsx`
 * (`MarkdownBlock`), the existing platform convention for rendering
 * untrusted markdown bodies: plain text via `whitespace-pre-wrap`, never
 * `dangerouslySetInnerHTML`. */
export function MarkdownBlock({ value }: { value: string }) {
  return (
    <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-relaxed text-foreground">
      {value}
    </pre>
  );
}

export function EmptyState({ message }: { message: string }) {
  return (
    <div className="py-12 text-center text-sm text-muted-foreground">{message}</div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div role="alert" className="py-12 text-center text-sm text-destructive">
      {message}
    </div>
  );
}
