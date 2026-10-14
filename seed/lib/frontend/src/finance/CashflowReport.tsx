/**
 * `<CashflowReport/>` — fluxo de caixa: what actually moved (realizado, from the ledger) and what is
 * still expected (projetado, open entries by due date), by month, with a chart and a table.
 * Transfers between the org's own accounts net to zero in the all-accounts view.
 */
import * as React from 'react';
import { BarChart } from '../design-system/charts/BarChart';
import { ChartCard } from '../design-system/charts/ChartCard';
import { StatTile } from '../design-system/charts/StatTile';
import { StatTileRow } from '../design-system/charts/StatTileRow';
import { Field, Input, PageHeader, RefreshingBar, Select } from './controls';
import { formatCents, formatMonth, monthEndIso, monthStartIso } from './format';
import { errorMessage, type FinanceHooks } from './hooks';
import { t } from './i18n';

export interface CashflowReportProps {
  hooks: FinanceHooks;
  /** Clock seam for tests (defaults to now). */
  now?: Date;
}

export function CashflowReport({ hooks, now }: CashflowReportProps) {
  const base = React.useMemo(() => now ?? new Date(), [now]);
  const [from, setFrom] = React.useState(monthStartIso(base));
  const [to, setTo] = React.useState(monthEndIso(base, 5));
  const [accountId, setAccountId] = React.useState('');
  const accounts = hooks.useAccounts();
  const report = hooks.useCashflow({ from, to, account_id: accountId });

  const buckets = report.data?.buckets ?? [];
  const chartData = buckets.map((b) => ({
    month: formatMonth(b.month),
    realized_in: b.realized_in_cents,
    realized_out: b.realized_out_cents,
    projected_in: b.projected_in_cents,
    projected_out: b.projected_out_cents,
  }));
  const hasMoney = !!report.data && Object.values(report.data.totals).some((v) => v !== 0);
  const totals = report.data?.totals;

  return (
    <section className="space-y-4" aria-busy={report.isRefreshing}>
      <PageHeader title={t('cashflow.title')} subtitle={t('cashflow.subtitle')} />
      <div className="grid gap-2 sm:grid-cols-3">
        <Field label={t('report.from')}><Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></Field>
        <Field label={t('report.to')}><Input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></Field>
        <Field label={t('report.account')}>
          <Select value={accountId} onChange={(e) => setAccountId(e.target.value)}>
            <option value="">{t('report.all_accounts')}</option>
            {(accounts.data ?? []).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </Select>
        </Field>
      </div>
      <RefreshingBar active={report.isRefreshing} label={t('common.refreshing')} />
      <StatTileRow>
        <StatTile label={t('cashflow.opening')} value={formatCents(report.data?.opening_balance_cents)} loading={report.showSkeleton} />
        <StatTile label={t('cashflow.closing_realized')} value={formatCents(report.data?.closing_realized_balance_cents)} hint={t('cashflow.closing_realized_hint')} loading={report.showSkeleton} />
        <StatTile label={t('cashflow.closing_projected')} value={formatCents(report.data?.closing_projected_balance_cents)} hint={t('cashflow.closing_projected_hint')} loading={report.showSkeleton} />
      </StatTileRow>
      <ChartCard
        title={t('cashflow.chart_title')}
        loading={report.showSkeleton}
        error={report.isError && !report.data ? `${t('common.error_loading')}: ${errorMessage(report.error)}` : null}
        isEmpty={!report.showSkeleton && !!report.data && !hasMoney}
        emptyMessage={t('cashflow.empty')}
      >
        <BarChart
          data={chartData}
          xKey="month"
          height={260}
          valueFormatter={(v) => formatCents(v)}
          series={[
            { key: 'realized_in', label: t('cashflow.realized_in') },
            { key: 'realized_out', label: t('cashflow.realized_out') },
            { key: 'projected_in', label: t('cashflow.projected_in') },
            { key: 'projected_out', label: t('cashflow.projected_out') },
          ]}
        />
      </ChartCard>
      {buckets.length > 0 ? (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-xs text-muted-foreground">
              <th className="p-2">{t('report.month')}</th>
              <th className="p-2 text-right">{t('cashflow.realized_in')}</th>
              <th className="p-2 text-right">{t('cashflow.realized_out')}</th>
              <th className="p-2 text-right">{t('cashflow.projected_in')}</th>
              <th className="p-2 text-right">{t('cashflow.projected_out')}</th>
            </tr>
          </thead>
          <tbody>
            {buckets.map((b) => (
              <tr key={b.month} className="border-b">
                <td className="p-2">{formatMonth(b.month)}</td>
                <td className="p-2 text-right">{formatCents(b.realized_in_cents)}</td>
                <td className="p-2 text-right">{formatCents(b.realized_out_cents)}</td>
                <td className="p-2 text-right">{formatCents(b.projected_in_cents)}</td>
                <td className="p-2 text-right">{formatCents(b.projected_out_cents)}</td>
              </tr>
            ))}
          </tbody>
          {totals ? (
            <tfoot>
              <tr className="font-semibold">
                <td className="p-2">{t('report.total')}</td>
                <td className="p-2 text-right">{formatCents(totals.realized_in_cents)}</td>
                <td className="p-2 text-right">{formatCents(totals.realized_out_cents)}</td>
                <td className="p-2 text-right">{formatCents(totals.projected_in_cents)}</td>
                <td className="p-2 text-right">{formatCents(totals.projected_out_cents)}</td>
              </tr>
            </tfoot>
          ) : null}
        </table>
      ) : null}
    </section>
  );
}
