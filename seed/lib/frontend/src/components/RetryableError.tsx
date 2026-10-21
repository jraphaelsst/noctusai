/**
 * RetryableError / QueryErrorState — the canonical "it failed, try again"
 * surface shown once the automatic attempts (`../retry`) ran out.
 *
 * Owner request (2026-10-21): retry automatically, paced; after a few
 * attempts stop and give the user a button that triggers the same process.
 * The automatic part lives in `createQueryClient` (queries) and
 * `useRetryableAction` (processes); this is the button.
 *
 * Copy: the title ("Não foi possível carregar." by default), a short reason
 * CLASS from `describeFailure` — never the server's raw text — and, when the
 * failure was transient and more than one attempt ran, "Tentamos N vezes
 * automaticamente." so the user knows clicking is not the first try.
 *
 * Two-signal rule (KB § PATTERNS/frontend/lying-loading-state.md): this
 * REPLACES content only when there is no data. `QueryErrorState` renders
 * nothing while the query still has data (a failed background refetch keeps
 * the last good data on screen; the toast already said it failed), and the
 * caller's skeleton owns the first load (`showSkeleton = isPending && !data`).
 *
 *     if (q.showSkeleton) return <Skeleton />;
 *     if (q.isError && !q.data) return <QueryErrorState query={q} />;
 *
 * Accessibility: `role="alert"` announces the failure; the button is a real
 * focusable `<button>`, `aria-busy` while the retry is in flight.
 */
import { AlertCircle, Loader2, RefreshCw } from 'lucide-react';
import type { ReactNode } from 'react';
import { toast } from 'sonner';

import { Button } from '../design-system/ui/Button';
import { describeFailure, isTransientError } from '../retry';
import { cn } from '../utils';

export const RETRYABLE_ERROR_MESSAGES = {
  titleLoad: 'Não foi possível carregar.',
  retry: 'Tentar novamente',
  retrying: 'Tentando…',
  autoAttempts: (n: number) => `Tentamos ${n} vezes automaticamente.`,
} as const;

export interface RetryableErrorProps {
  /** The failure — only its CLASS is shown (`describeFailure`), never its text. */
  error?: unknown;
  /** Re-runs the same process (`query.refetch`, `action.retry`, ...). */
  onRetry: () => unknown;
  /** A retry is in flight — spinner + disabled button. */
  isRetrying?: boolean;
  /** Total attempts already made (e.g. `query.failureCount`). The
   *  "Tentamos N vezes" line shows only for a transient failure with N > 1. */
  attempts?: number;
  /** Defaults to "Não foi possível carregar." */
  title?: string;
  /** Overrides the reason line (e.g. a domain-specific explanation). */
  description?: ReactNode;
  /** `block` (default) — centered panel replacing a section; `inline` — a
   *  compact row inside a card. */
  variant?: 'block' | 'inline';
  /** Extra actions next to the retry button (e.g. a "Voltar" link). */
  actions?: ReactNode;
  className?: string;
  'data-testid'?: string;
}

export function RetryableError({
  error,
  onRetry,
  isRetrying = false,
  attempts,
  title = RETRYABLE_ERROR_MESSAGES.titleLoad,
  description,
  variant = 'block',
  actions,
  className,
  'data-testid': testId = 'retryable-error',
}: RetryableErrorProps) {
  const reason = description ?? (error !== undefined && error !== null ? describeFailure(error) : null);
  const showAuto = !isRetrying && attempts !== undefined && attempts > 1 && isTransientError(error);
  const button = (
    <Button
      variant="outline"
      size="sm"
      onClick={() => void onRetry()}
      disabled={isRetrying}
      aria-busy={isRetrying || undefined}
      data-testid={`${testId}-retry`}
    >
      {isRetrying ? (
        <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
      ) : (
        <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
      )}
      {isRetrying ? RETRYABLE_ERROR_MESSAGES.retrying : RETRYABLE_ERROR_MESSAGES.retry}
    </Button>
  );

  if (variant === 'inline') {
    return (
      <div
        role="alert"
        data-testid={testId}
        className={cn(
          'flex flex-wrap items-center justify-between gap-3 rounded-md border border-destructive/30 bg-destructive/5 p-2.5 text-xs',
          className,
        )}
      >
        <div className="min-w-0 space-y-0.5">
          <p className="font-medium text-destructive">{title}</p>
          {reason && <p className="text-muted-foreground">{reason}</p>}
          {showAuto && <p className="text-muted-foreground">{RETRYABLE_ERROR_MESSAGES.autoAttempts(attempts!)}</p>}
        </div>
        <div className="flex items-center gap-2">
          {actions}
          {button}
        </div>
      </div>
    );
  }

  return (
    <div
      role="alert"
      data-testid={testId}
      className={cn('flex flex-col items-center gap-2 py-10 text-center text-sm', className)}
    >
      <AlertCircle className="h-8 w-8 text-destructive" aria-hidden="true" />
      <p className="font-medium">{title}</p>
      {reason && <p className="max-w-md text-muted-foreground">{reason}</p>}
      {showAuto && (
        <p className="max-w-md text-xs text-muted-foreground">
          {RETRYABLE_ERROR_MESSAGES.autoAttempts(attempts!)}
        </p>
      )}
      <div className="mt-1 flex flex-wrap items-center justify-center gap-2">
        {button}
        {actions}
      </div>
    </div>
  );
}

/** The slice of a TanStack `useQuery` result `QueryErrorState` reads. */
export interface RetryableQueryLike {
  error: unknown;
  isError: boolean;
  isFetching: boolean;
  failureCount: number;
  data?: unknown;
  refetch: () => unknown;
}

export interface QueryErrorStateProps
  extends Omit<RetryableErrorProps, 'error' | 'onRetry' | 'isRetrying' | 'attempts'> {
  query: RetryableQueryLike;
}

/**
 * `RetryableError` bound to a query: the button calls `refetch()` (which runs
 * the same paced automatic attempts again), the spinner follows `isFetching`,
 * the attempt count is the query's `failureCount`. Renders nothing unless the
 * query is in error WITHOUT data — a failed background refetch never replaces
 * data that is still on screen.
 */
export function QueryErrorState({ query, ...rest }: QueryErrorStateProps) {
  if (!query.isError || query.data !== undefined) return null;
  return (
    <RetryableError
      {...rest}
      error={query.error}
      onRetry={() => query.refetch()}
      isRetrying={query.isFetching}
      // `failureCount` resets to 0 when a refetch starts; it is the attempt
      // total of the run that just failed once the query settles in error.
      attempts={query.isFetching ? undefined : query.failureCount}
    />
  );
}

/**
 * Toast variant for a PROCESS that failed after its automatic attempts (an
 * upload fired from a button deep in a dialog, where there is no section to
 * replace): same copy, with "Tentar novamente" as the toast action.
 */
export function toastRetryableError(options: {
  title: string;
  error: unknown;
  attempts?: number;
  onRetry: () => unknown;
}): void {
  const { title, error, attempts, onRetry } = options;
  const parts = [describeFailure(error)];
  if (attempts !== undefined && attempts > 1 && isTransientError(error)) {
    parts.push(RETRYABLE_ERROR_MESSAGES.autoAttempts(attempts));
  }
  toast.error(title, {
    description: parts.join(' '),
    action: { label: RETRYABLE_ERROR_MESSAGES.retry, onClick: () => void onRetry() },
  });
}
