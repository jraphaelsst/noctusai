/**
 * Dialog — minimal inline modal primitive (no Radix dependency).
 *
 * Usage:
 *   <Dialog open={open} onClose={handleClose} title="Detalhes">
 *     <p>Body content</p>
 *   </Dialog>
 *
 * Structure:
 *   Backdrop (fixed inset-0, bg-black/50) →
 *     Panel (white card, rounded-lg, max-w-md, border-border) →
 *       children
 *
 * Accessibility:
 *   - role="dialog" aria-modal="true" on the backdrop
 *   - aria-label={title} when title is provided
 *   - Escape key calls onClose
 *   - Clicking the backdrop calls onClose
 *   - Click propagation stopped inside the panel
 *
 * NOTE: This is a controlled component — open state is managed by the caller.
 * For complex dialogs with headers/footers, compose using DialogHeader /
 * DialogFooter sub-components (exported alongside Dialog).
 */
import * as React from "react";
import { cn } from "../../utils";

// ── Sub-components ────────────────────────────────────────────────────────────

export interface DialogHeaderProps extends React.HTMLAttributes<HTMLDivElement> {}

export function DialogHeader({ className, children, ...props }: DialogHeaderProps) {
  return (
    <div
      className={cn(
        "flex items-start justify-between gap-3 border-b border-border px-6 py-4",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}
DialogHeader.displayName = "DialogHeader";

export interface DialogBodyProps extends React.HTMLAttributes<HTMLDivElement> {}

export function DialogBody({ className, children, ...props }: DialogBodyProps) {
  return (
    <div
      className={cn("max-h-[70vh] overflow-y-auto px-6 py-5", className)}
      {...props}
    >
      {children}
    </div>
  );
}
DialogBody.displayName = "DialogBody";

export interface DialogFooterProps extends React.HTMLAttributes<HTMLDivElement> {}

export function DialogFooter({ className, children, ...props }: DialogFooterProps) {
  return (
    <div
      className={cn(
        "flex justify-end border-t border-border px-6 py-4",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}
DialogFooter.displayName = "DialogFooter";

// ── Dialog ────────────────────────────────────────────────────────────────────

export interface DialogProps {
  /** When false the dialog is not rendered (null return). */
  open: boolean;
  /** Called when the user closes via Escape or clicking the backdrop. */
  onClose: () => void;
  /** Used as aria-label on the dialog root. */
  title?: string;
  /** Extra className applied to the inner panel. */
  className?: string;
  children: React.ReactNode;
}

export function Dialog({ open, onClose, title, className, children }: DialogProps) {
  React.useEffect(() => {
    if (!open) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    /* Backdrop */
    <div
      role="dialog"
      aria-modal="true"
      aria-label={title}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      {/* Panel */}
      <div
        className={cn(
          "relative w-full max-w-2xl rounded-lg border border-border bg-background shadow-lg",
          className,
        )}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}
Dialog.displayName = "Dialog";
