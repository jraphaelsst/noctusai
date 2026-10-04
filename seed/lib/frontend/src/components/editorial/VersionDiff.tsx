/**
 * `<VersionDiff/>` — compares two immutable editorial versions. JSON content
 * gets a structured per-field diff (`diffContent`); string fields that hold
 * prose (markdown) render both sides through the canonical `MarkdownRenderer`.
 * Pass `before`/`after` directly, or pass `dataSource`+`itemId`+`fromN`/`toN`
 * to fetch via `EditorialDataSource.diff`.
 */
import * as React from 'react';
import { useQuery } from '@tanstack/react-query';
import { AlertCircle, Loader2, RefreshCw } from 'lucide-react';

import { Badge } from '../../design-system/ui/Badge';
import { Button } from '../../design-system/ui/Button';
import { cn } from '../../utils';
import { MarkdownRenderer } from '../markdown';
import { diffContent, hasChanges } from './diffContent';
import type { FieldChange, FieldChangeKind } from './diffContent';
import type { EditorialDataSource, EditorialVersion } from './types';

export interface VersionDiffProps {
  /** Direct mode. */
  before?: EditorialVersion | null;
  after?: EditorialVersion | null;
  /** Fetch mode (used when `dataSource` is given). */
  dataSource?: EditorialDataSource;
  itemId?: string;
  fromN?: number;
  toN?: number;
  /** Field names (last path segment) rendered as markdown. */
  markdownFields?: string[];
  /** Hide fields that did not change. Default true. */
  onlyChanged?: boolean;
  title?: string;
}

const DEFAULT_MD_FIELDS = ['corpo', 'body', 'markdown', 'conteudo', 'content', 'texto'];

const KIND_META: Record<FieldChangeKind, { label: string; cls: string }> = {
  added: { label: 'Adicionado', cls: 'border-green-500/30 bg-green-500/10 text-green-700 dark:text-green-400' },
  removed: { label: 'Removido', cls: 'border-destructive/30 bg-destructive/10 text-destructive' },
  changed: { label: 'Alterado', cls: 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400' },
  unchanged: { label: 'Igual', cls: 'border-border bg-muted text-muted-foreground' },
};

function ValueView({
  value,
  markdown,
}: {
  value: unknown;
  markdown: boolean;
}): React.ReactElement {
  if (value === undefined) return <span className="text-muted-foreground">—</span>;
  if (markdown && typeof value === 'string') return <MarkdownRenderer content={value} />;
  const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  return <pre className="whitespace-pre-wrap break-words text-sm">{text}</pre>;
}

export function VersionDiff(props: VersionDiffProps): React.ReactElement {
  const {
    dataSource,
    itemId,
    fromN,
    toN,
    markdownFields = DEFAULT_MD_FIELDS,
    onlyChanged = true,
    title = 'Comparar versões',
  } = props;

  const fetchMode = !!dataSource && !!itemId && fromN != null && toN != null;
  const query = useQuery({
    queryKey: ['editorial-diff', itemId, fromN, toN],
    queryFn: () => dataSource!.diff(itemId!, fromN!, toN!),
    enabled: fetchMode,
    placeholderData: (prev) => prev,
  });

  const before = fetchMode ? query.data?.from : props.before;
  const after = fetchMode ? query.data?.to : props.after;
  const hasData = fetchMode ? !!query.data : !!(before && after);
  const showSkeleton = fetchMode && query.isPending && !query.data;
  const isRefreshing = fetchMode && query.isFetching && !!query.data;

  let body: React.ReactNode;
  if (showSkeleton) {
    body = (
      <div aria-busy="true" className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Carregando versões…
      </div>
    );
  } else if (fetchMode && query.isError && !query.data) {
    body = (
      <div
        role="alert"
        className="flex items-start justify-between gap-3 rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive"
      >
        <span className="flex items-start gap-2">
          <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" />
          {query.error instanceof Error ? query.error.message : 'Não foi possível comparar as versões.'}
        </span>
        <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
          <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
          Tentar novamente
        </Button>
      </div>
    );
  } else if (!hasData || !before || !after) {
    body = (
      <p className="py-6 text-sm text-muted-foreground">
        Selecione duas versões para comparar.
      </p>
    );
  } else {
    const all = diffContent(before.content, after.content);
    const shown: FieldChange[] = onlyChanged ? all.filter((c) => c.kind !== 'unchanged') : all;
    body = !hasChanges(all) ? (
      <p className="py-6 text-sm text-muted-foreground">
        As versões v{before.n} e v{after.n} têm o mesmo conteúdo.
      </p>
    ) : (
      <ul className="space-y-4">
        {shown.map((c) => {
          const meta = KIND_META[c.kind];
          const leaf = c.path.split('.').pop() ?? c.path;
          const md = markdownFields.includes(leaf);
          return (
            <li key={c.path} className="rounded-md border border-border">
              <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-2">
                <code className="text-sm font-medium">{c.path}</code>
                <Badge variant="outline" className={cn('font-medium', meta.cls)}>
                  {meta.label}
                </Badge>
              </div>
              <div className="grid gap-3 p-3 sm:grid-cols-2">
                <div>
                  <p className="mb-1 text-xs font-medium text-muted-foreground">v{before.n}</p>
                  <ValueView value={c.before} markdown={md} />
                </div>
                <div>
                  <p className="mb-1 text-xs font-medium text-muted-foreground">v{after.n}</p>
                  <ValueView value={c.after} markdown={md} />
                </div>
              </div>
            </li>
          );
        })}
      </ul>
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

VersionDiff.displayName = 'VersionDiff';
