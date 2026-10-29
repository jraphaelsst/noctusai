/**
 * `<ClientsList/>` -- every client of the org: search (name / phone / e-mail), status + tag filters, name order,
 * "Carregar mais" pages (cursor). Columns: name · coloured status · tags · next session · open amount. A row opens
 * the client (host navigation); "Novo" creates one. The noun ("Pacientes") is the product's config.
 */
import { Plus } from 'lucide-react';
import * as React from 'react';

import { Button } from '../design-system/ui/Button';
import { useDebounced } from '../leads/useLeadFilters';
import { formatCents } from '../organ-kit/money';
import { ClientFormDialog } from './ClientForm';
import { EmptyState, Input, ListSkeleton, RefreshingBar, RetryError, Select } from './controls';
import { formatWhen, hasClientFilters, optionOf, tzOf } from './format';
import { errorMessage, type ClientsHooks } from './hooks';
import { t } from './i18n';
import { nounVars, TagChips, ToneBadge } from './parts';
import type { Client, ClientFiltersState } from './types';

export interface ClientsListProps {
  hooks: ClientsHooks;
  /** Host navigation to the client's page. */
  onOpenClient: (client: Client) => void;
  /** Hide "Novo". */
  readOnly?: boolean;
  /** Initial filters (e.g. from the URL). */
  initialFilters?: ClientFiltersState;
}

export function ClientsList({ hooks, onOpenClient, readOnly, initialFilters }: ClientsListProps) {
  const { data: config } = hooks.useClientsConfig();
  const tags = hooks.useClientTags();
  const [filters, setFilters] = React.useState<ClientFiltersState>(initialFilters ?? {});
  const [text, setText] = React.useState(initialFilters?.q ?? '');
  const q = useDebounced(text);
  React.useEffect(() => {
    setFilters((f) => ((f.q ?? '') === q ? f : { ...f, q: q || undefined }));
  }, [q]);
  const list = hooks.useClientsList(filters);
  const [creating, setCreating] = React.useState(false);
  const vars = nounVars(config);
  const tz = tzOf(config);
  const rows = list.data ?? [];

  return (
    <div className="space-y-3" data-testid="clients-list">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div className="flex min-w-0 flex-1 flex-wrap items-end gap-2" data-testid="clients-filters">
          <div className="min-w-[14rem] flex-1">
            <Input type="search" aria-label={t('filters.search')} placeholder={t('filters.search')} value={text} onChange={(e) => setText(e.target.value)} />
          </div>
          <div className="w-44">
            <Select aria-label={t('filters.status')} value={filters.status ?? ''} onChange={(e) => setFilters({ ...filters, status: e.target.value || undefined })}>
              <option value="">{t('filters.all_statuses')}</option>
              {config?.statuses.map((s) => (
                <option key={s.slug} value={s.slug}>
                  {s.label}
                </option>
              ))}
            </Select>
          </div>
          <div className="w-44">
            <Select aria-label={t('filters.tag')} value={filters.tag ?? ''} onChange={(e) => setFilters({ ...filters, tag: e.target.value || undefined })}>
              <option value="">{t('filters.all_tags')}</option>
              {(tags.data ?? []).map((tag) => (
                <option key={tag} value={tag}>
                  {tag}
                </option>
              ))}
            </Select>
          </div>
          {hasClientFilters(filters) && (
            <Button
              variant="ghost"
              onClick={() => {
                setText('');
                setFilters({});
              }}
            >
              {t('filters.clear')}
            </Button>
          )}
        </div>
        {!readOnly && (
          <Button onClick={() => setCreating(true)} data-testid="clients-new">
            <Plus className="mr-1 h-4 w-4" />
            {t('list.new', vars)}
          </Button>
        )}
      </div>
      <RefreshingBar active={list.isRefreshing} label={t('common.refreshing')} />
      {list.showSkeleton ? (
        <ListSkeleton />
      ) : list.isError && !list.data ? (
        <RetryError message={`${t('list.error', vars)} ${errorMessage(list.error)}`} onRetry={() => void list.refetch()} retryLabel={t('common.retry')} />
      ) : rows.length === 0 ? (
        <EmptyState message={hasClientFilters(filters) ? t('list.empty_filtered', vars) : t('list.empty', vars)} />
      ) : (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                {['name', 'status', 'tags', 'next', 'open'].map((c) => (
                  <th key={c} className={c === 'open' ? 'px-3 py-2 text-right font-medium' : 'px-3 py-2 font-medium'}>
                    {t(`list.col_${c}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => {
                const status = optionOf(config?.statuses, c.status);
                return (
                  <tr key={c.id} className="cursor-pointer border-t hover:bg-muted/40" onClick={() => onOpenClient(c)} data-testid={`client-row-${c.id}`}>
                    <td className="px-3 py-2 font-medium">{c.name}</td>
                    <td className="px-3 py-2">
                      <ToneBadge color={status.color}>{status.label}</ToneBadge>
                    </td>
                    <td className="px-3 py-2">
                      <TagChips tags={c.tags} />
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">{formatWhen(c.summary.next_session_at, tz) || '—'}</td>
                    <td className={c.summary.overdue_cents > 0 ? 'px-3 py-2 text-right font-medium text-destructive' : 'px-3 py-2 text-right'}>
                      {c.summary.open_cents > 0 ? formatCents(c.summary.open_cents) : '—'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {list.hasNextPage && (
        <div className="text-center">
          <Button variant="outline" disabled={list.isFetchingNextPage} onClick={() => void list.fetchNextPage()}>
            {list.isFetchingNextPage ? t('list.loading_more') : t('list.more')}
          </Button>
        </div>
      )}
      <ClientFormDialog hooks={hooks} open={creating} client={null} onClose={() => setCreating(false)} onSaved={onOpenClient} />
    </div>
  );
}
