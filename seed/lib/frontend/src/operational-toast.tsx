/**
 * Operational toast -- the neutral pop-up for something that HAPPENED which the user did not trigger
 * (a new lead, a Vista sync applied, an approval pending).
 *
 * Two notification classes, never mixed (KB § PATTERNS/frontend/notification-classes.md):
 *   - feedback    -> `toast.success` / `toast.error` (green / red): the result of what the user just did.
 *   - operational -> THIS: neutral surface, title + message, X to close, ~8 s, pauses on hover, click opens `link`.
 */
import { Bell, X } from "lucide-react";
import { toast } from "sonner";

export const OPERATIONAL_TOAST_MS = 8000;

export interface ToastOperacionalOptions {
  title: string;
  message?: string | null;
  /** Shown only to decide whether the card is clickable; navigation is the caller's (`onOpen`). */
  link?: string | null;
  /** Click on the card body (not on the X). Receives the toast id so the caller can dismiss it. */
  onOpen?: () => void;
  /** Stable id: the same id replaces a toast instead of stacking a duplicate. */
  id?: string | number;
  durationMs?: number;
}

/** Show a neutral operational pop-up. Returns the toast id. */
export function toastOperacional({ title, message, link, onOpen, id, durationMs = OPERATIONAL_TOAST_MS }: ToastOperacionalOptions): string | number {
  const clickable = !!onOpen && (link === undefined || !!link);
  return toast.custom(
    (tid) => (
      <div
        role="status"
        data-testid="toast-operacional"
        onClick={clickable ? () => { onOpen?.(); toast.dismiss(tid); } : undefined}
        className={`pointer-events-auto flex w-[356px] max-w-[calc(100vw-2rem)] items-start gap-3 rounded-lg border border-border bg-card p-3 text-card-foreground shadow-lg ${
          clickable ? "cursor-pointer hover:bg-accent" : ""
        }`}
      >
        <Bell className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium leading-snug">{title}</p>
          {message ? <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{message}</p> : null}
        </div>
        <button
          type="button"
          aria-label="Fechar notificação"
          onClick={(e) => { e.stopPropagation(); toast.dismiss(tid); }}
          className="shrink-0 rounded p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
    ),
    { id, duration: durationMs },
  );
}
