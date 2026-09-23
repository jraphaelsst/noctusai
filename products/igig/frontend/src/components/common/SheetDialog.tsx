/**
 * SheetDialog — igig's modal shell: a full-screen sheet below 640px, a
 * centered panel above (roadmap R0, mobile-first).
 *
 * Composition only — the Radix dialog is the seed's (`CardHubDialogRoot` /
 * `CardHubDialogContent`, `@noctusai/lib/design-system`); every mobile rule is
 * a `max-sm:` utility, the same convention the seed `CardHubDialog` uses, so
 * desktop keeps the design-system defaults. Header and footer stay put while
 * the body scrolls; the body never scrolls sideways.
 */
import type { ReactNode } from "react";
import {
  CardHubDialogContent,
  CardHubDialogDescription,
  CardHubDialogRoot,
  CardHubDialogTitle,
} from "@noctusai/lib/design-system";
import { cn } from "@noctusai/lib";

export interface SheetDialogProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  description?: ReactNode;
  /** Beside the title (status badge, version…). */
  headerExtra?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
  /** Desktop width. Default `sm:max-w-2xl`. */
  widthClassName?: string;
  testId?: string;
}

export function SheetDialog({
  open,
  onClose,
  title,
  description,
  headerExtra,
  footer,
  children,
  widthClassName = "sm:max-w-2xl",
  testId,
}: SheetDialogProps) {
  return (
    <CardHubDialogRoot open={open} onOpenChange={(o) => (o ? undefined : onClose())}>
      <CardHubDialogContent
        data-testid={testId}
        className={cn(
          "flex max-h-[92dvh] flex-col gap-0 p-0",
          widthClassName,
          // < 640px: full-screen sheet on the VISIBLE viewport height.
          "max-sm:inset-0 max-sm:left-0 max-sm:top-0 max-sm:h-[100dvh] max-sm:max-h-[100dvh] max-sm:max-w-none max-sm:translate-x-0 max-sm:translate-y-0 max-sm:rounded-none max-sm:border-0",
        )}
      >
        <div className="flex items-start gap-2 border-b border-border px-4 py-3 pr-12 sm:px-6">
          <div className="min-w-0 flex-1">
            <CardHubDialogTitle className="truncate text-base sm:text-lg">{title}</CardHubDialogTitle>
            {description ? (
              <CardHubDialogDescription className="mt-0.5 text-xs">{description}</CardHubDialogDescription>
            ) : (
              <CardHubDialogDescription className="sr-only">{String(title)}</CardHubDialogDescription>
            )}
          </div>
          {headerExtra}
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-4 py-4 sm:px-6">{children}</div>
        {footer ? (
          <div className="border-t border-border bg-background px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:px-6">
            {footer}
          </div>
        ) : null}
      </CardHubDialogContent>
    </CardHubDialogRoot>
  );
}
