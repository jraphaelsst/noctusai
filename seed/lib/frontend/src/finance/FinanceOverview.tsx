/**
 * `<FinanceOverview/>` — visão geral: balance per account, open receivables / payables, what is overdue,
 * and this month's result. Every card loads and fails on its own (one slow report never blanks the page).
 */
import * as React from 'react';
import { ChartCard } from '../design-system/charts/ChartCard';
import { DonutChart } from '../design-system/charts/DonutChart';
import { StatTile } from '../design-system/charts/StatTile';
import { StatTileRow } from '../design-system/charts/StatTileRow';
import { Button } from '../design-system/ui/Button';
import { Notice, PageHeader, RefreshingBar } from './controls';
import { formatCents, monthEndIso, monthStartIso, remainingCents } from './format';
import { errorMessage, type FinanceHooks } from './hooks';
import { t } from './i18n';

export interface FinanceOverviewProps {
  hooks: FinanceHooks;
  now?: Date;
  /** Optional deep links (the host routes). */
  onNavigate?: (section: 'receivable' | 'payable' | 'cashflow' | 'accounts') => void;
}

export function FinanceOverview({ hooks, now, onNavigate }: FinanceOverviewProps) {
  const base = React.useMemo(() => now ?? new Date(), [now]);
  const accounts = hooks.useAccounts({ active: true });
  const ids = React.useMemo(() => (accounts.data ?? []).map((a) => a.id), [accounts.data]);
  const balances = hooks.useAccountBalances(ids);
  const cash = hooks.useCashflow({ from: monthStartIso(base), to: monthEndIso(base, 5) });
  const aging = hooks.useAging();
  const overduePayable = hooks.useEntries({ direction: 'payable', overdue: true, page: 1, page_size: 100 });

  const accountRows = (accounts.data ?? []).map((a) => ({ id: a.id, name: a.name, balance: balances.byId[a.id]?.balance_cents }));
  const totalBalance = accountRows.reduce((sum, r) => sum + (r.balance ?? 0), 0);
  const balancesKnown = accountRows.length > 0 && accountRows.every((r) => r.balance !== undefined);
  const slices = accountRows.filter((r) => (r.balance ?? 0) > 0).map((r) => ({ name: r.name, value: r.balance as number }));

  const thisMonth = cash.data?.buckets[0];
  const monthResult = thisMonth ? thisMonth.realized_in_cents - thisMonth.realized_out_cents : undefined;
  const apRows = overduePayable.data?.data ?? [];
  const apTotal = apRows.reduce((s, e) => s + remainingCents(e), 0);
  const apCount = overduePayable.data?.pagination.total ?? 0;
  const apPartial = apCount > apRows.length;

  const failures: { key: string; message: string; retry: () => void }[] = [];
  if (accounts.isError && !accounts.data) failures.push({ key: 'accounts', message: t('overview.err_accounts'), retry: () => void accounts.refetch() });
  if (cash.isError && !cash.data) failures.push({ key: 'cash', message: t('overview.err_cashflow'), retry: () => void cash.refetch() });
  if (aging.isError && !aging.data) failures.push({ key: 'aging', message: t('overview.err_aging'), retry: () => void aging.refetch() });
  if (overduePayable.isError && !overduePayable.data) failures.push({ key: 'payable', message: t('overview.err_payable'), retry: () => void overduePayable.refetch() });

  const refreshing = accounts.isRefreshing || balances.isRefreshing || cash.isRefreshing || aging.isRefreshing || overduePayable.isRefreshing;

  return (
    <section className="space-y-4" aria-busy={refreshing}>
      <PageHeader title={t('overview.title')} subtitle={t('overview.subtitle')} />
      <RefreshingBar active={refreshing} label={t('common.refreshing')} />
      {failures.map((f) => (
        <Notice key={f.key} tone="critical">
          {f.message}{' '}
          <Button size="sm" variant="outline" onClick={f.retry}>{t('common.retry')}</Button>
        </Notice>
      ))}
      <StatTileRow>
        <StatTile
          label={t('overview.total_balance')}
          value={balancesKnown ? formatCents(totalBalance) : '—'}
          hint={t('overview.total_balance_hint')}
          loading={accounts.showSkeleton || balances.showSkeleton}
        />
        <StatTile
          label={t('overview.to_receive')}
          value={cash.data ? formatCents(cash.data.totals.projected_in_cents) : '—'}
          hint={t('overview.window_hint')}
          loading={cash.showSkeleton}
        />
        <StatTile
          label={t('overview.to_pay')}
          value={cash.data ? formatCents(cash.data.totals.projected_out_cents) : '—'}
          hint={t('overview.window_hint')}
          loading={cash.showSkeleton}
        />
        <StatTile
          label={t('overview.month_result')}
          value={monthResult === undefined ? '—' : formatCents(monthResult)}
          hint={t('overview.month_result_hint')}
          loading={cash.showSkeleton}
        />
      </StatTileRow>
      <StatTileRow>
        <StatTile
          label={t('overview.overdue_receivable')}
          value={aging.data ? formatCents(aging.data.totals.total_cents) : '—'}
          hint={aging.data ? t('overview.overdue_customers', { n: aging.data.counterparties.length }) : undefined}
          loading={aging.showSkeleton}
        />
        <StatTile
          label={t('overview.overdue_payable')}
          value={overduePayable.data ? formatCents(apTotal) : '—'}
          hint={overduePayable.data ? (apPartial ? t('overview.overdue_payable_partial', { n: apRows.length, total: apCount }) : t('overview.overdue_entries', { n: apCount })) : undefined}
          loading={overduePayable.showSkeleton}
        />
      </StatTileRow>
      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard
          title={t('overview.balances_title')}
          loading={accounts.showSkeleton || balances.showSkeleton}
          error={accounts.isError && !accounts.data ? t('overview.err_accounts') : null}
          isEmpty={!accounts.showSkeleton && (accounts.data ?? []).length === 0}
          emptyMessage={t('accounts.empty')}
          actions={onNavigate ? <Button size="sm" variant="ghost" onClick={() => onNavigate('accounts')}>{t('overview.see_accounts')}</Button> : undefined}
        >
          <ul className="space-y-1 text-sm" aria-label={t('overview.balances_title')}>
            {accountRows.map((r) => (
              <li key={r.id} className="flex justify-between">
                <span>{r.name}</span>
                <span>{r.balance === undefined ? '…' : formatCents(r.balance)}</span>
              </li>
            ))}
          </ul>
          {slices.length > 0 ? <DonutChart data={slices} nameKey="name" valueKey="value" height={200} valueFormatter={(v) => formatCents(v)} /> : null}
        </ChartCard>
        <ChartCard
          title={t('overview.next_title')}
          loading={cash.showSkeleton}
          error={cash.isError && !cash.data ? `${t('common.error_loading')}: ${errorMessage(cash.error)}` : null}
          isEmpty={!cash.showSkeleton && !!cash.data && cash.data.buckets.length === 0}
          emptyMessage={t('cashflow.empty')}
          actions={onNavigate ? <Button size="sm" variant="ghost" onClick={() => onNavigate('cashflow')}>{t('overview.see_cashflow')}</Button> : undefined}
        >
          <dl className="space-y-1 text-sm">
            <div className="flex justify-between"><dt>{t('overview.closing_projected')}</dt><dd>{formatCents(cash.data?.closing_projected_balance_cents)}</dd></div>
            <div className="flex justify-between"><dt>{t('overview.month_in')}</dt><dd>{formatCents(thisMonth?.realized_in_cents)}</dd></div>
            <div className="flex justify-between"><dt>{t('overview.month_out')}</dt><dd>{formatCents(thisMonth?.realized_out_cents)}</dd></div>
          </dl>
        </ChartCard>
      </div>
    </section>
  );
}
