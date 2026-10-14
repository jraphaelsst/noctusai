/** `<AgingReport/>` — inadimplência: overdue receivables by customer and age bucket (remaining amount, not face value). */
import * as React from 'react';
import { EmptyState, Field, Input, ListSkeleton, PageHeader, RefreshingBar, RetryError } from './controls';
import { formatCents, formatDate } from './format';
import { errorMessage, type FinanceHooks } from './hooks';
import { t } from './i18n';
import { AGING_BUCKET_KEYS } from './types';

export interface AgingReportProps {
  hooks: FinanceHooks;
}

export function AgingReport({ hooks }: AgingReportProps) {
  const [asOf, setAsOf] = React.useState('');
  const report = hooks.useAging(asOf || undefined);

  let body: React.ReactNode;
  if (report.showSkeleton) body = <ListSkeleton rows={5} />;
  else if (report.isError && !report.data) {
    body = <RetryError message={`${t('common.error_loading')}: ${errorMessage(report.error)}`} onRetry={() => report.refetch()} retryLabel={t('common.retry')} />;
  } else if (report.data && report.data.counterparties.length === 0) {
    body = <EmptyState message={t('aging.empty')} />;
  } else if (report.data) {
    const d = report.data;
    body = (
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-xs text-muted-foreground">
            <th className="p-2">{t('aging.counterparty')}</th>
            {AGING_BUCKET_KEYS.map((k) => <th key={k} className="p-2 text-right">{t(`aging.bucket_${k}`)}</th>)}
            <th className="p-2 text-right">{t('report.total')}</th>
            <th className="p-2">{t('aging.oldest')}</th>
          </tr>
        </thead>
        <tbody>
          {d.counterparties.map((c, i) => (
            <tr key={`${c.counterparty_doc ?? c.counterparty_name ?? '-'}-${i}`} className="border-b">
              <td className="p-2">
                {c.counterparty_name ?? '—'}
                {c.counterparty_doc ? <div className="text-xs text-muted-foreground">{c.counterparty_doc}</div> : null}
                <div className="text-xs text-muted-foreground">{t('aging.entries', { n: c.entries })}</div>
              </td>
              {AGING_BUCKET_KEYS.map((k) => <td key={k} className="p-2 text-right">{formatCents(c.buckets[k])}</td>)}
              <td className="p-2 text-right font-medium">{formatCents(c.total_cents)}</td>
              <td className="p-2">{formatDate(c.oldest_due_date)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="font-semibold">
            <td className="p-2">{t('report.total')}</td>
            {AGING_BUCKET_KEYS.map((k) => <td key={k} className="p-2 text-right">{formatCents(d.totals.buckets[k])}</td>)}
            <td className="p-2 text-right">{formatCents(d.totals.total_cents)}</td>
            <td />
          </tr>
        </tfoot>
      </table>
    );
  }

  return (
    <section className="space-y-3" aria-busy={report.isRefreshing}>
      <PageHeader title={t('aging.title')} subtitle={t('aging.subtitle')} />
      <div className="max-w-xs">
        <Field label={t('aging.as_of')}><Input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} /></Field>
      </div>
      <RefreshingBar active={report.isRefreshing} label={t('common.refreshing')} />
      {body}
    </section>
  );
}
