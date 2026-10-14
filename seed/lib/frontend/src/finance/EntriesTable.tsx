/**
 * `<EntriesTable/>` — contas a receber / contas a pagar. Filters by status, period, category, text
 * and "vencidos"; create / edit dialog, baixa (also partial), cancel, estorno and attachments via the
 * detail dialog. Pass `direction` to fix the side ("Contas a receber" page); omit for both.
 * Writes are admin-only (`isAdmin`); the server enforces it again.
 */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { EmptyState, EntryStatusChip, Input, ListSkeleton, PageHeader, Pager, RefreshingBar, RetryError, Select, totalPagesOf } from './controls';
import { EntryDetailDialog } from './EntryDetailDialog';
import { EntryDialog } from './EntryDialog';
import { SettleDialog } from './SettleDialog';
import { formatCents, formatDate, remainingCents } from './format';
import { errorMessage, type FinanceHooks } from './hooks';
import { t } from './i18n';
import { ENTRY_STATUSES, type EntryDirection, type EntryStatus, type FinanceEntry } from './types';

export interface EntriesTableProps {
  hooks: FinanceHooks;
  /** Fixes the side. Without it a direction filter is shown. */
  direction?: EntryDirection;
  isAdmin?: boolean;
  pageSize?: number;
}

export function EntriesTable({ hooks, direction, isAdmin = false, pageSize = 20 }: EntriesTableProps) {
  const [dirFilter, setDirFilter] = React.useState<EntryDirection | ''>('');
  const [status, setStatus] = React.useState<EntryStatus | ''>('');
  const [overdue, setOverdue] = React.useState(false);
  const [from, setFrom] = React.useState('');
  const [to, setTo] = React.useState('');
  const [categoryId, setCategoryId] = React.useState('');
  const [q, setQ] = React.useState('');
  const [page, setPage] = React.useState(1);

  const [detailId, setDetailId] = React.useState<string | null>(null);
  const [editing, setEditing] = React.useState<FinanceEntry | 'new' | null>(null);
  const [settling, setSettling] = React.useState<FinanceEntry | null>(null);

  const effectiveDir = direction ?? dirFilter;
  const entries = hooks.useEntries({
    direction: effectiveDir,
    status,
    overdue: overdue || undefined,
    from,
    to,
    category_id: categoryId,
    q,
    page,
    page_size: pageSize,
  });
  const categories = hooks.useCategories();
  const catName = (id: string | null) => categories.data?.find((c) => c.id === id)?.name ?? '—';
  const resetPage = <T,>(set: (v: T) => void) => (v: T) => {
    set(v);
    setPage(1);
  };

  const title = direction === 'receivable' ? t('entries.title_receivable') : direction === 'payable' ? t('entries.title_payable') : t('entries.title_all');
  const catOptions = (categories.data ?? []).filter((c) => !direction || c.direction === (direction === 'receivable' ? 'income' : 'expense'));

  let body: React.ReactNode;
  if (entries.showSkeleton) body = <ListSkeleton rows={6} />;
  else if (entries.isError && !entries.data) {
    body = <RetryError message={`${t('common.error_loading')}: ${errorMessage(entries.error)}`} onRetry={() => entries.refetch()} retryLabel={t('common.retry')} />;
  } else {
    const rows = entries.data?.data ?? [];
    body = rows.length === 0 ? (
      <EmptyState message={t('entries.empty')} />
    ) : (
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-xs text-muted-foreground">
            <th className="p-2">{t('entry.due_date')}</th>
            <th className="p-2">{t('entry.description')}</th>
            <th className="p-2">{t('entry.category')}</th>
            <th className="p-2 text-right">{t('entry.amount')}</th>
            <th className="p-2 text-right">{t('entry.remaining')}</th>
            <th className="p-2">{t('entry.status')}</th>
            <th className="p-2"><span className="sr-only">{t('common.actions')}</span></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((e) => {
            const open = e.status === 'open' || e.status === 'partial';
            return (
              <tr key={e.id} className="border-b hover:bg-accent/50">
                <td className="p-2 whitespace-nowrap">{formatDate(e.due_date)}</td>
                <td className="p-2">
                  <button type="button" className="text-left underline-offset-2 hover:underline" onClick={() => setDetailId(e.id)}>
                    {e.description}
                  </button>
                  {e.counterparty_name ? <div className="text-xs text-muted-foreground">{e.counterparty_name}</div> : null}
                  {e.installment_n && e.installment_total ? <div className="text-xs text-muted-foreground">{t('entry.installment')} {e.installment_n}/{e.installment_total}</div> : null}
                </td>
                <td className="p-2">{catName(e.category_id)}</td>
                <td className="p-2 text-right whitespace-nowrap">{formatCents(e.amount_cents)}</td>
                <td className="p-2 text-right whitespace-nowrap">{formatCents(remainingCents(e))}</td>
                <td className="p-2"><EntryStatusChip status={e.status} overdue={e.overdue} /></td>
                <td className="p-2 text-right whitespace-nowrap">
                  {isAdmin && open ? (
                    <Button size="sm" variant="outline" onClick={() => setSettling(e)} aria-label={`${t('entry.settle')}: ${e.description}`}>
                      {t('entry.settle')}
                    </Button>
                  ) : null}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    );
  }

  return (
    <section className="space-y-3" aria-busy={entries.isRefreshing}>
      <PageHeader
        title={title}
        actions={isAdmin ? <Button size="sm" onClick={() => setEditing('new')}>{t('entries.new')}</Button> : undefined}
      />
      <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-6">
        {!direction ? (
          <Select aria-label={t('entries.filter_direction')} value={dirFilter} onChange={(e) => resetPage(setDirFilter)(e.target.value as EntryDirection | '')}>
            <option value="">{t('entries.all_directions')}</option>
            <option value="receivable">{t('entry.direction_receivable')}</option>
            <option value="payable">{t('entry.direction_payable')}</option>
          </Select>
        ) : null}
        <Select aria-label={t('entries.filter_status')} value={status} onChange={(e) => resetPage(setStatus)(e.target.value as EntryStatus | '')}>
          <option value="">{t('common.all')}</option>
          {ENTRY_STATUSES.map((s) => (
            <option key={s} value={s}>{t(`entry_status.${s}`)}</option>
          ))}
        </Select>
        <Select aria-label={t('entries.filter_category')} value={categoryId} onChange={(e) => resetPage(setCategoryId)(e.target.value)}>
          <option value="">{t('entries.all_categories')}</option>
          {catOptions.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </Select>
        <Input type="date" aria-label={t('entries.from')} value={from} onChange={(e) => resetPage(setFrom)(e.target.value)} />
        <Input type="date" aria-label={t('entries.to')} value={to} onChange={(e) => resetPage(setTo)(e.target.value)} />
        <Input type="search" aria-label={t('entries.search')} placeholder={t('entries.search')} value={q} onChange={(e) => resetPage(setQ)(e.target.value)} />
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={overdue} onChange={(e) => resetPage(setOverdue)(e.target.checked)} />
        {t('entries.only_overdue')}
      </label>
      <RefreshingBar active={entries.isRefreshing} label={t('common.refreshing')} />
      {body}
      <Pager page={page} totalPages={totalPagesOf(entries.data?.pagination)} onPage={setPage} />

      <EntryDetailDialog
        hooks={hooks}
        entryId={detailId}
        isAdmin={isAdmin}
        onClose={() => setDetailId(null)}
        onEdit={(e) => setEditing(e)}
        onSettle={(e) => setSettling(e)}
      />
      {isAdmin && editing !== null ? (
        <EntryDialog
          hooks={hooks}
          open
          direction={direction ?? (dirFilter || 'receivable')}
          entry={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
        />
      ) : null}
      {isAdmin && settling ? (
        <SettleDialog hooks={hooks} open entry={settling} onClose={() => setSettling(null)} />
      ) : null}
    </section>
  );
}
