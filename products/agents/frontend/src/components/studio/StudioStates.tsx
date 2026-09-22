/**
 * Loading / error / empty blocks shared by the Agent Studio pages and tabs —
 * ONLY the shapes `@noctusai/lib/design-system`'s `EmptyState`/`ErrorState`
 * don't cover; every call site that needed nothing more than a message was
 * switched to the lib components directly (no product-local fork of an
 * equivalent). What stays here, and why the lib doesn't have it:
 *   - `StudioLoading` — a row-COUNT-configurable skeleton (`rows`); the lib's
 *     only skeletons are the fixed-shape `PageSkeleton` and the raw
 *     `Skeleton` primitive.
 *   - `StudioError` — every call site passes `onRetry` and/or a `mensagem`
 *     override; the lib's `ErrorState` is message-only, no retry action.
 *   - `StudioEmpty` — some call sites pass `children` (a CTA below the
 *     title, e.g. "Novo agente"/"Criar rascunho"); the lib's `EmptyState`
 *     takes a single `message` string only.
 */
import type { ReactNode } from "react";
import { AlertTriangle, Inbox } from "lucide-react";
import { Button, Skeleton } from "@noctusai/lib/design-system";
import { errorMessage } from "@/lib/errors";

export function StudioLoading({ rows = 3, testId }: { rows?: number; testId?: string }) {
  return (
    <div className="space-y-3" data-testid={testId ?? "studio-loading"}>
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} height={i === 0 ? 36 : 72} announce={i === 0} />
      ))}
    </div>
  );
}

export function StudioError({
  error,
  onRetry,
  mensagem,
}: {
  error: unknown;
  onRetry?: () => void;
  mensagem?: string;
}) {
  return (
    <div
      className="flex flex-col items-center gap-2 rounded-lg border border-border bg-card p-8 text-center text-muted-foreground"
      role="alert"
      data-testid="studio-error"
    >
      <AlertTriangle className="h-6 w-6 text-destructive" />
      <p className="text-sm">{mensagem ?? errorMessage(error)}</p>
      {onRetry && (
        <Button size="sm" variant="outline" onClick={onRetry}>
          Tentar novamente
        </Button>
      )}
    </div>
  );
}

export function StudioEmpty({ titulo, children }: { titulo: string; children?: ReactNode }) {
  return (
    <div
      className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-border bg-card p-8 text-center text-muted-foreground"
      data-testid="studio-empty"
    >
      <Inbox className="h-6 w-6" />
      <p className="text-sm font-medium text-foreground">{titulo}</p>
      {children}
    </div>
  );
}
