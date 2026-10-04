/**
 * `<EditorialTimeline/>` — the append-only audit trail of one editorial item:
 * who did what, when, why (motivo) and on which version. Presentational: the
 * host passes `events` (from `EditorialDataSource.getItem`) plus its own
 * query flags, so it composes with any fetching layer.
 *
 * Loading contract (lying-loading-state): pass `isPending` as
 * `isPending && !data` semantics — i.e. only true while there is NO events
 * data yet; `isRefreshing` is an indicator only.
 */
import * as React from 'react';
import { AlertCircle, Loader2, RefreshCw } from 'lucide-react';

import { Badge } from '../../design-system/ui/Badge';
import { Button } from '../../design-system/ui/Button';
import { cn } from '../../utils';
import { ACTION_LABEL, STATE_META, formatWhen, stateLabel } from './labels';
import type { EditorialAction, EditorialEvent } from './types';

export interface EditorialTimelineProps {
  events: EditorialEvent[] | undefined;
  /** True only while there is no data yet (`isPending && !data`). */
  isPending?: boolean;
  /** Background refetch with data on screen — shows an indicator only. */
  isRefreshing?: boolean;
  error?: Error | null;
  onRetry?: () => void;
  /** Resolve an actor id to a display name; defaults to the raw id. */
  actorName?: (actorId: string) => string;
  title?: string;
}

export function EditorialTimeline(props: EditorialTimelineProps): React.ReactElement {
  const {
    events,
    isPending = false,
    isRefreshing = false,
    error = null,
    onRetry,
    actorName = (id) => id,
    title = 'Histórico editorial',
  } = props;

  let body: React.ReactNode;
  if (isPending && !events) {
    body = (
      <div
        aria-busy="true"
        className="flex items-center gap-2 py-6 text-sm text-muted-foreground"
      >
        <Loader2 className="h-4 w-4 animate-spin" />
        Carregando histórico…
      </div>
    );
  } else if (error && !events) {
    body = (
      <div
        role="alert"
        className="flex items-start justify-between gap-3 rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive"
      >
        <span className="flex items-start gap-2">
          <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" />
          {error.message || 'Não foi possível carregar o histórico.'}
        </span>
        {onRetry && (
          <Button variant="outline" size="sm" onClick={onRetry}>
            <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
            Tentar novamente
          </Button>
        )}
      </div>
    );
  } else if (!events || events.length === 0) {
    body = (
      <p className="py-6 text-sm text-muted-foreground">Nenhum evento registrado ainda.</p>
    );
  } else {
    const ordered = [...events].sort(
      (a, b) => a.created_at.localeCompare(b.created_at) || a.id - b.id,
    );
    body = (
      <ol className="space-y-4 border-l border-border pl-5">
        {ordered.map((ev) => {
          const toMeta = STATE_META[ev.to_state];
          const verb = ACTION_LABEL[ev.action as EditorialAction] ?? ev.action;
          return (
            <li key={ev.id} className="relative">
              <span
                aria-hidden="true"
                className="absolute -left-[26px] top-1.5 h-2 w-2 rounded-full bg-primary"
              />
              <p className="text-sm">
                <span className="font-medium">{actorName(ev.actor_id)}</span> {verb}
                <span className="text-muted-foreground"> · v{ev.version_n}</span>
              </p>
              <p className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <time dateTime={ev.created_at}>{formatWhen(ev.created_at)}</time>
                {ev.from_state !== ev.to_state && (
                  <span className="flex items-center gap-1">
                    {stateLabel(ev.from_state)} →{' '}
                    <Badge variant="outline" className={cn('font-medium', toMeta?.badgeClass)}>
                      {stateLabel(ev.to_state)}
                    </Badge>
                  </span>
                )}
                {ev.grant && <span>permissão: {ev.grant}</span>}
              </p>
              {ev.motivo && (
                <p className="mt-1 rounded-md bg-muted px-3 py-2 text-sm">
                  <span className="font-medium">Motivo:</span> {ev.motivo}
                </p>
              )}
            </li>
          );
        })}
      </ol>
    );
  }

  return (
    <section
      aria-label={title}
      className="rounded-lg border border-border bg-card text-card-foreground shadow-sm"
    >
      <header className="border-b border-border px-5 py-4">
        <h3 className="flex items-center gap-2 text-base font-semibold leading-none tracking-tight">
          {title}
          {isRefreshing && (
            <Loader2
              role="status"
              aria-label="Atualizando"
              className="h-3.5 w-3.5 animate-spin text-muted-foreground"
            />
          )}
        </h3>
      </header>
      <div className="px-5 py-4">{body}</div>
    </section>
  );
}

EditorialTimeline.displayName = 'EditorialTimeline';
