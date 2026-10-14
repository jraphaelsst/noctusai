/**
 * `<SimplesBaseReport/>` — "Base do Simples": receita bruta for the DAS check (sales + installment interest, commission
 * NOT netted, minus cancellations/refunds; juros de mora excluded; lost chargebacks shown but NOT deducted). Cash basis
 * (recebimento) until 2026-12, faturamento (approximated by the receivable's competence month) from 2027-01 — Res. CGSN
 * 190/2026. Helps the owner conferir the PGDAS-D number; never files anything. `GET /api/finance/reports/simples-base`.
 */
import * as React from 'react';
import { EmptyState, Field, Input, ListSkeleton, Notice, PageHeader, RefreshingBar, RetryError } from './controls';
import { formatCents, formatDate, formatMonth, todayIso } from './format';
import { errorMessage, type FinanceHooks } from './hooks';
import { t } from './i18n';

export interface SimplesBaseReportProps {
  hooks: FinanceHooks;
  now?: Date;
}

export function SimplesBaseReport({ hooks, now }: SimplesBaseReportProps) {
  const base = React.useMemo(() => now ?? new Date(), [now]);
  const [from, setFrom] = React.useState(`${base.getFullYear()}-01-01`);
  const [to, setTo] = React.useState(todayIso(base));
  const report = hooks.useSimplesBase({ from, to });

  let body: React.ReactNode;
  if (report.showSkeleton) body = <ListSkeleton rows={5} />;
  else if (report.isError && !report.data) {
    body = <RetryError message={`${t('common.error_loading')}: ${errorMessage(report.error)}`} onRetry={() => report.refetch()} retryLabel={t('common.retry')} />;
  } else if (report.data) {
    const d = report.data;
    body = (
      <>
        {d.warnings.map((w) => (
          <Notice key={w.code} tone={w.severity === 'critical' ? 'critical' : w.severity === 'warning' ? 'warning' : 'info'}>
            <span data-warning={w.code}>{w.message}</span>
            {w.action ? <span className="mt-0.5 block text-xs">{t('dre.what_to_do')}: {w.action}</span> : null}
          </Notice>
        ))}
        <Notice tone="info">
          {t('simples.basis_rule', { date: formatDate(d.invoice_basis_from) })}
          {d.crosses_basis_boundary ? <span className="block text-xs">{t('simples.crosses_boundary')}</span> : null}
        </Notice>
        <dl className="grid gap-2 text-sm sm:grid-cols-2">
          <div className="flex justify-between rounded-md border p-2"><dt>{t('simples.sales')}</dt><dd>{formatCents(d.totals.sales_cents)}</dd></div>
          <div className="flex justify-between rounded-md border p-2"><dt>{t('simples.interest')}</dt><dd>{formatCents(d.totals.interest_cents)}</dd></div>
          <div className="flex justify-between rounded-md border p-2"><dt>{t('simples.refunds')}</dt><dd>− {formatCents(d.totals.refunds_cents)}</dd></div>
          <div className="flex justify-between rounded-md border bg-muted p-2 font-semibold"><dt>{t('simples.base')}</dt><dd>{formatCents(d.totals.base_cents)}</dd></div>
        </dl>
        {d.totals.chargebacks_cents > 0 ? (
          <p className="text-xs text-muted-foreground">{t('simples.chargebacks_note', { amount: formatCents(d.totals.chargebacks_cents) })}</p>
        ) : null}
        {d.months.length === 0 ? (
          <EmptyState message={t('simples.empty')} />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th className="p-2">{t('report.month')}</th>
                <th className="p-2">{t('simples.basis')}</th>
                <th className="p-2 text-right">{t('simples.sales')}</th>
                <th className="p-2 text-right">{t('simples.interest')}</th>
                <th className="p-2 text-right">{t('simples.refunds')}</th>
                <th className="p-2 text-right">{t('simples.base')}</th>
              </tr>
            </thead>
            <tbody>
              {d.months.map((mo) => (
                <tr key={mo.month} className="border-b">
                  <td className="p-2">{formatMonth(mo.month)}</td>
                  <td className="p-2 text-xs">{mo.basis === 'cash' ? t('simples.basis_cash') : t('simples.basis_invoice')}</td>
                  <td className="p-2 text-right">{formatCents(mo.sales_cents)}</td>
                  <td className="p-2 text-right">{formatCents(mo.interest_cents)}</td>
                  <td className="p-2 text-right">{formatCents(mo.refunds_cents)}</td>
                  <td className="p-2 text-right font-medium">{formatCents(mo.base_cents)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="text-xs text-muted-foreground">{d.basis_note}</p>
        {d.notes.length > 0 ? <ul className="list-disc pl-5 text-xs text-muted-foreground">{d.notes.map((n, i) => <li key={i}>{n}</li>)}</ul> : null}
      </>
    );
  }

  return (
    <section className="space-y-3" aria-busy={report.isRefreshing}>
      <PageHeader title={t('simples.title')} subtitle={t('simples.subtitle')} />
      <div className="grid max-w-md gap-2 sm:grid-cols-2">
        <Field label={t('report.from')}><Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></Field>
        <Field label={t('report.to')}><Input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></Field>
      </div>
      <RefreshingBar active={report.isRefreshing} label={t('common.refreshing')} />
      {body}
      <p className="text-xs text-muted-foreground">{t('simples.disclaimer')}</p>
    </section>
  );
}
