/**
 * `<ReviewQueue/>` — editorial review queue: items filterable by state (with
 * per-state counts) and an "awaiting me" filter, paged.
 *
 * Data comes through the typed `EditorialDataSource` seam (see README.md).
 * Loading follows KB § PATTERNS/frontend/lying-loading-state.md:
 * `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`
 * (indicator only), `placeholderData: prev` across filter/page changes.
 * Requires a `QueryClientProvider` in the host tree.
 */
import * as React from 'react';
import { useQuery } from '@tanstack/react-query';
import { AlertCircle, Loader2, RefreshCw } from 'lucide-react';

import { Badge } from '../../design-system/ui/Badge';
import { Button } from '../../design-system/ui/Button';
import { cn } from '../../utils';
import { STATE_META, formatWhen } from './labels';
import { EDITORIAL_STATES } from './types';
import type { EditorialDataSource, EditorialItem, EditorialState } from './types';

export interface ReviewQueueProps {
  dataSource: EditorialDataSource;
  /** Called when the user opens an item. */
  onSelect?: (item: EditorialItem) => void;
  /** Initial state filter (`null` = all). Default `null`. */
  initialState?: EditorialState | null;
  /** Initial "awaiting me" filter. Default `false`. */
  initialAwaitingMe?: boolean;
  pageSize?: number;
  /** Section title. Default "Fila editorial". */
  title?: string;
  /** Query-key namespace so several queues can coexist. */
  queryKeyPrefix?: string;
}

export function ReviewQueue(props: ReviewQueueProps): React.ReactElement {
  const {
    dataSource,
    onSelect,
    initialState = null,
    initialAwaitingMe = false,
    pageSize = 20,
    title = 'Fila editorial',
    queryKeyPrefix = 'editorial-queue',
  } = props;

  const [state, setState] = React.useState<EditorialState | null>(initialState);
  const [awaitingMe, setAwaitingMe] = React.useState(initialAwaitingMe);
  const [page, setPage] = React.useState(1);

  const query = useQuery({
    queryKey: [queryKeyPrefix, { state, awaitingMe, page, pageSize }],
    queryFn: () =>
      dataSource.listQueue({ state, awaiting_me: awaitingMe, page, page_size: pageSize }),
    placeholderData: (prev) => prev,
  });

  const data = query.data;
  const showSkeleton = query.isPending && !data;
  const isRefreshing = query.isFetching && !!data;

  const pickState = (s: EditorialState | null) => {
    setState(s);
    setPage(1);
  };

  const totalCount = data
    ? EDITORIAL_STATES.reduce((acc, s) => acc + (data.counts[s] ?? 0), 0)
    : null;
  const totalPages = data ? Math.max(1, Math.ceil(data.total / pageSize)) : 1;

  let body: React.ReactNode;
  if (showSkeleton) {
    body = (
      <div
        aria-busy="true"
        className="flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground"
      >
        <Loader2 className="h-4 w-4 animate-spin" />
        Carregando fila…
      </div>
    );
  } else if (query.isError && !data) {
    const message =
      query.error instanceof Error ? query.error.message : 'Não foi possível carregar a fila.';
    body = (
      <div
        role="alert"
        className="flex items-start justify-between gap-3 rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive"
      >
        <span className="flex items-start gap-2">
          <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" />
          {message}
        </span>
        <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
          <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
          Tentar novamente
        </Button>
      </div>
    );
  } else if (!data || data.items.length === 0) {
    body = (
      <p className="py-8 text-center text-sm text-muted-foreground">
        {awaitingMe
          ? 'Nada aguardando a sua ação.'
          : state
            ? `Nenhum item em "${STATE_META[state].label}".`
            : 'Nenhum item editorial ainda.'}
      </p>
    );
  } else {
    body = (
      <>
        <ul className="divide-y divide-border rounded-md border border-border">
          {data.items.map((item) => {
            const meta = STATE_META[item.state];
            return (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => onSelect?.(item)}
                  className="flex w-full flex-col gap-1 px-4 py-3 text-left hover:bg-muted/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 sm:flex-row sm:items-center sm:justify-between"
                >
                  <span className="min-w-0">
                    <span className="block truncate font-medium">{item.title || item.ref}</span>
                    <span className="block truncate text-xs text-muted-foreground">
                      {item.kind} · v{item.current_version_n}
                      {item.published_version_n != null
                        ? ` · publicada v${item.published_version_n}`
                        : ''}{' '}
                      · atualizado {formatWhen(item.updated_at)}
                    </span>
                  </span>
                  <Badge variant="outline" className={cn('font-medium', meta.badgeClass)}>
                    {meta.label}
                  </Badge>
                </button>
              </li>
            );
          })}
        </ul>
        {totalPages > 1 && (
          <nav aria-label="Paginação" className="mt-3 flex items-center justify-end gap-2 text-sm">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Anterior
            </Button>
            <span aria-live="polite">
              Página {page} de {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            >
              Próxima
            </Button>
          </nav>
        )}
      </>
    );
  }

  return (
    <section
      aria-label={title}
      className="rounded-lg border border-border bg-card text-card-foreground shadow-sm"
    >
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4">
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
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={awaitingMe}
            onChange={(e) => {
              setAwaitingMe(e.target.checked);
              setPage(1);
            }}
          />
          Aguardando minha ação
        </label>
      </header>
      <div className="px-5 py-4">
        <div role="group" aria-label="Filtrar por estado" className="mb-4 flex flex-wrap gap-2">
          <Button
            variant={state === null ? 'primary' : 'outline'}
            size="sm"
            aria-pressed={state === null}
            onClick={() => pickState(null)}
          >
            Todos{totalCount != null ? ` (${totalCount})` : ''}
          </Button>
          {EDITORIAL_STATES.map((s) => (
            <Button
              key={s}
              variant={state === s ? 'primary' : 'outline'}
              size="sm"
              aria-pressed={state === s}
              onClick={() => pickState(s)}
            >
              {STATE_META[s].label}
              {data ? ` (${data.counts[s] ?? 0})` : ''}
            </Button>
          ))}
        </div>
        {body}
      </div>
    </section>
  );
}

ReviewQueue.displayName = 'ReviewQueue';
