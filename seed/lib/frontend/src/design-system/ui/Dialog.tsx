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
 *     Panel (white card, rounded-lg, max-w-md default, border-border) →
 *       children
 *
 * Accessibility:
 *   - role="dialog" aria-modal="true" on the backdrop
 *   - aria-label={title} when title is provided
 *   - Escape key calls onClose
 *   - Clicking the backdrop calls onClose — but ONLY when the press both
 *     started and ended there, so a text-selection drag that starts inside
 *     the panel and releases over the backdrop never closes the dialog
 *     (it used to, discarding whatever the user had typed)
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
      // overflow-x-hidden: prevents horizontal scrollbar when a child (e.g. a long
      // URL, token, or ID) is wider than the panel. Combined with break-words/break-all
      // on value text, this is the design-system default: content wraps, never scrolls
      // sideways. overflow-y-auto remains for tall content.
      className={cn("max-h-[70vh] overflow-y-auto overflow-x-hidden px-6 py-5", className)}
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
  /** Where the current press STARTED — see the backdrop's onMouseDown/onClick. */
  const pressOriginRef = React.useRef<"backdrop" | "panel" | null>(null);

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
      /* A backdrop `click` alone is NOT enough to mean "clicked outside": a
         drag that STARTS inside the panel (select-all in a text field, drag a
         slider) and RELEASES over the backdrop still fires `click` on their
         common ancestor — the backdrop — and would close the dialog, losing
         whatever the user had typed. So the close requires BOTH ends of the
         gesture on the backdrop: `mousedown` arms it, `click` acts on it. */
      onMouseDown={(e) => {
        pressOriginRef.current = e.target === e.currentTarget ? "backdrop" : "panel";
      }}
      onClick={(e) => {
        const fromBackdrop = pressOriginRef.current !== "panel";
        pressOriginRef.current = null;
        if (e.target === e.currentTarget && fromBackdrop) onClose();
      }}
    >
      {/* Panel */}
      <div
        className={cn(
          "relative w-full max-w-md rounded-lg border border-border bg-background shadow-lg",
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
