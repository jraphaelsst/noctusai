/**
 * `<ContractsTable/>` — searchable, filterable, paged list of contracts with status badges, a create / edit dialog
 * (`<ContractEditor/>`). Two-signal loading: a skeleton on the FIRST load only; a refetch over data shows a small
 * indicator and never unmounts the table. `party_doc` is masked by the server for non-admins. `canWrite` is UX only.
 */
import * as React from 'react';
import { Badge } from '../design-system/ui/Badge';
import { Button } from '../design-system/ui/Button';
import { ContractEditor, type ContractEditorProps } from './ContractEditor';
import { EmptyState, Input, ListSkeleton, RefreshingBar, RetryError, Select } from './controls';
import { contractsErrorText } from './errors';
import { amountLabel, formatDate } from './format';
import type { ContractsHooks } from './hooks';
import { t } from './i18n';
import { CONTRACT_BILLING_MODELS, CONTRACT_STATUSES, type ContractBillingModel, type ContractStatus } from './types';

export interface ContractsTableProps {
  hooks: ContractsHooks;
  canWrite?: boolean;
  pageSize?: number;
  initialStatus?: ContractStatus | '';
  /** Row click override; default opens the built-in `<ContractEditor/>`. */
  onSelect?: (id: string) => void;
  renderPartyPicker?: ContractEditorProps['renderPartyPicker'];
}

const STATUS_VARIANT = { draft: 'muted', active: 'default', suspended: 'outline', terminated: 'destructive', expired: 'muted' } as const;

export function ContractsTable({ hooks, canWrite = false, pageSize = 20, initialStatus = '', onSelect, renderPartyPicker }: ContractsTableProps) {
  const [q, setQ] = React.useState('');
  const [debounced, setDebounced] = React.useState('');
  const [status, setStatus] = React.useState<ContractStatus | ''>(initialStatus);
  const [model, setModel] = React.useState<ContractBillingModel | ''>('');
  const [page, setPage] = React.useState(1);
  const [editing, setEditing] = React.useState<string | 'new' | null>(null);

  React.useEffect(() => {
    const h = setTimeout(() => { setDebounced(q.trim()); setPage(1); }, 300);
    return () => clearTimeout(h);
  }, [q]);

  const list = hooks.useContracts({ q: debounced, status, billing_model: model, page, page_size: pageSize });

  let content: React.ReactNode;
  if (list.showSkeleton) {
    content = <ListSkeleton rows={6} />;
  } else if (list.isError && !list.data) {
    content = <RetryError message={`${t('common.error_loading')}: ${contractsErrorText(list.error)}`} onRetry={() => list.refetch()} retryLabel={t('common.retry')} />;
  } else {
    const rows = list.data?.data ?? [];
    const pg = list.data?.pagination;
    const totalPages = pg ? (pg.total_pages ?? Math.max(1, Math.ceil(pg.total / pg.page_size))) : 1;
    const filtered = !!(debounced || status || model);
    content = (
      <>
        <RefreshingBar active={list.isRefreshing} label={t('common.refreshing')} />
        {rows.length === 0 ? (
          <EmptyState message={filtered ? t('contracts.empty_search') : t('contracts.empty')} />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th className="p-2">{t('contracts.col_title')}</th>
                <th className="p-2">{t('contracts.col_party')}</th>
                <th className="p-2">{t('contracts.col_model')}</th>
                <th className="p-2 text-right">{t('contracts.col_amount')}</th>
                <th className="p-2">{t('contracts.col_term')}</th>
                <th className="p-2">{t('contracts.col_status')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr
                  key={c.id}
                  tabIndex={0}
                  className="cursor-pointer border-b hover:bg-accent focus:bg-accent"
                  onClick={() => (onSelect ? onSelect(c.id) : setEditing(c.id))}
                  onKeyDown={(e) => { if (e.key === 'Enter') (onSelect ? onSelect(c.id) : setEditing(c.id)); }}
                >
                  <td className="p-2">
                    <div className="font-medium">{c.title}</div>
                    {c.number ? <div className="text-xs text-muted-foreground">{c.number}</div> : null}
                  </td>
                  <td className="p-2">{c.party_name ?? '—'}</td>
                  <td className="p-2">{t(`model.${c.billing_model}`)}</td>
                  <td className="p-2 text-right tabular-nums">{amountLabel(c.billing_model, c.amount_cents)}</td>
                  <td className="p-2 text-xs">
                    {formatDate(c.start_date)} {c.end_date ? t('contracts.until', { date: formatDate(c.end_date) }) : t('contracts.indefinite')}
                    {c.lapsed ? <Badge variant="destructive" className="ml-1">{t('contracts.lapsed')}</Badge> : null}
                  </td>
                  <td className="p-2"><Badge variant={STATUS_VARIANT[c.status]}>{t(`status.${c.status}`)}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {totalPages > 1 ? (
          <div className="flex items-center justify-end gap-2 text-sm">
            <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage((n) => n - 1)}>{t('common.previous')}</Button>
            <span>{page} / {totalPages}</span>
            <Button size="sm" variant="outline" disabled={page >= totalPages} onClick={() => setPage((n) => n + 1)}>{t('common.next')}</Button>
          </div>
        ) : null}
      </>
    );
  }

  return (
    <section className="space-y-3" aria-busy={list.isRefreshing}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-semibold">{t('contracts.title')}</h2>
        {canWrite ? <Button size="sm" onClick={() => setEditing('new')}>{t('contracts.new')}</Button> : null}
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <div className="min-w-[14rem] flex-1">
          <Input type="search" aria-label={t('contracts.search')} placeholder={t('contracts.search')} value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <Select aria-label={t('contracts.filter_status')} value={status} onChange={(e) => { setStatus(e.target.value as ContractStatus | ''); setPage(1); }}>
          <option value="">{t('contracts.all_statuses')}</option>
          {CONTRACT_STATUSES.map((s) => <option key={s} value={s}>{t(`status.${s}`)}</option>)}
        </Select>
        <Select aria-label={t('contracts.filter_model')} value={model} onChange={(e) => { setModel(e.target.value as ContractBillingModel | ''); setPage(1); }}>
          <option value="">{t('contracts.all_models')}</option>
          {CONTRACT_BILLING_MODELS.map((m) => <option key={m} value={m}>{t(`model.${m}`)}</option>)}
        </Select>
      </div>
      {content}
      {editing !== null ? (
        <ContractEditor hooks={hooks} open contractId={editing === 'new' ? null : editing} onClose={() => setEditing(null)} canWrite={canWrite} renderPartyPicker={renderPartyPicker} />
      ) : null}
    </section>
  );
}
