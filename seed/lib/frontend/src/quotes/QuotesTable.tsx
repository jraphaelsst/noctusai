/**
 * `<QuotesTable/>` — searchable, filterable, paged list of quotes (current versions) with status chips, a create /
 * edit dialog (`<QuoteEditor/>`).
 *
 * Two-signal loading: a skeleton on the FIRST load only; a refetch over data shows a small indicator and never
 * unmounts the table (no lying empty state). `canWrite` is UX only — the server enforces admin-only writes.
 */
import * as React from 'react';
import { Button, EmptyState, Input, ListSkeleton, RefreshingBar, RetryError, Select } from './controls';
import { formatCents, formatDate } from './format';
import { errorMessage, type QuotesHooks } from './hooks';
import { defaultQuotesT, type QuotesTranslate } from './i18n';
import { QuoteConversionChip, QuoteStatusChip } from './QuoteStatusChip';
import { QuoteEditor, type QuoteEditorProps } from './QuoteEditor';
import { QUOTE_STATUSES, type QuoteItemOption, type QuotePartyOption, type QuoteStatus } from './types';

export interface QuotesTableProps {
  hooks: QuotesHooks;
  t?: QuotesTranslate;
  locale?: string;
  /** Admin write access (UX only). Default `false`. */
  canWrite?: boolean;
  pageSize?: number;
  /** Customer / item pickers for the built-in editor (the parties / items organs own those names). */
  parties?: QuotePartyOption[];
  items?: QuoteItemOption[];
  /** Row click override; default opens the built-in `<QuoteEditor/>`. */
  onSelect?: (id: string) => void;
  /** Forwarded to the editor (e.g. to wire the send dialog's copy of the PDF link). */
  editorProps?: Partial<Pick<QuoteEditorProps, 'pdfHref'>>;
}

export function QuotesTable({ hooks, t = defaultQuotesT, locale, canWrite = false, pageSize = 20, parties = [], items = [], onSelect, editorProps }: QuotesTableProps) {
  const [q, setQ] = React.useState('');
  const [debounced, setDebounced] = React.useState('');
  const [status, setStatus] = React.useState<QuoteStatus | ''>('');
  const [page, setPage] = React.useState(1);
  const [editing, setEditing] = React.useState<string | 'new' | null>(null);

  React.useEffect(() => {
    const h = setTimeout(() => {
      setDebounced(q.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(h);
  }, [q]);

  const list = hooks.useQuotes({ q: debounced, status, page, page_size: pageSize });
  const partyName = React.useMemo(() => new Map(parties.map((p) => [p.id, p.name])), [parties]);

  const header = (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h2 className="text-base font-semibold">{t('table.title')}</h2>
      {canWrite ? <Button size="sm" variant="primary" onClick={() => setEditing('new')}>{t('table.new')}</Button> : null}
    </div>
  );

  const controls = (
    <div className="flex flex-wrap items-end gap-2">
      <div className="min-w-[14rem] flex-1">
        <Input type="search" aria-label={t('table.search')} placeholder={t('table.search')} value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <Select aria-label={t('table.filter_status')} value={status} onChange={(e) => { setStatus(e.target.value as QuoteStatus | ''); setPage(1); }}>
        <option value="">{t('status.all')}</option>
        {QUOTE_STATUSES.map((s) => <option key={s} value={s}>{t(`status.${s}`)}</option>)}
      </Select>
    </div>
  );

  let content: React.ReactNode;
  if (list.showSkeleton) {
    content = <ListSkeleton rows={6} />;
  } else if (list.isError && !list.data) {
    content = <RetryError message={`${t('common.error_loading')}: ${errorMessage(list.error)}`} onRetry={() => list.refetch()} retryLabel={t('common.retry')} />;
  } else {
    const rows = list.data?.data ?? [];
    const pg = list.data?.pagination;
    const totalPages = pg ? (pg.total_pages ?? Math.max(1, Math.ceil(pg.total / pg.page_size))) : 1;
    const filtered = !!(debounced || status);
    const open = (id: string) => (onSelect ? onSelect(id) : setEditing(id));
    content = (
      <>
        <RefreshingBar active={list.isRefreshing} label={t('common.refreshing')} />
        {rows.length === 0 ? (
          <EmptyState message={filtered ? t('table.empty_filtered') : t('table.empty')} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-muted-foreground">
                  <th className="p-2">{t('table.col_number')}</th>
                  <th className="p-2">{t('table.col_party')}</th>
                  <th className="p-2">{t('table.col_title')}</th>
                  <th className="p-2 text-right">{t('table.col_total')}</th>
                  <th className="p-2">{t('table.col_valid')}</th>
                  <th className="p-2">{t('table.col_status')}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr
                    key={r.id}
                    data-testid="quote-row"
                    tabIndex={0}
                    className="cursor-pointer border-b hover:bg-accent focus:bg-accent"
                    onClick={() => open(r.id)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') open(r.id);
                    }}
                  >
                    <td className="p-2 font-medium tabular-nums">
                      {r.number} <span className="text-xs text-muted-foreground">{t('table.version', { n: r.version })}</span>
                    </td>
                    <td className="p-2">{r.party?.legal_name ?? partyName.get(r.party_id) ?? '—'}</td>
                    <td className="p-2">{r.title ?? '—'}</td>
                    <td className="p-2 text-right tabular-nums">{formatCents(r.total_cents, r.currency, locale)}</td>
                    <td className="p-2 tabular-nums">{formatDate(r.valid_until)}</td>
                    <td className="space-x-1 p-2">
                      <QuoteStatusChip status={r.status} t={t} />
                      <QuoteConversionChip status={r.conversion_status} t={t} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {totalPages > 1 ? (
          <div className="flex items-center justify-end gap-2 text-sm">
            <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage((n) => n - 1)}>{t('common.previous')}</Button>
            <span>{t('common.page', { page, pages: totalPages })}</span>
            <Button size="sm" variant="outline" disabled={page >= totalPages} onClick={() => setPage((n) => n + 1)}>{t('common.next')}</Button>
          </div>
        ) : null}
      </>
    );
  }

  return (
    <section className="space-y-3" aria-busy={list.isRefreshing} aria-label={t('table.title')}>
      {header}
      {controls}
      {content}
      {editing !== null ? (
        <QuoteEditor
          hooks={hooks}
          t={t}
          locale={locale}
          open
          quoteId={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
          onOpenQuote={(id) => setEditing(id)}
          canWrite={canWrite}
          parties={parties}
          items={items}
          {...editorProps}
        />
      ) : null}
    </section>
  );
}
