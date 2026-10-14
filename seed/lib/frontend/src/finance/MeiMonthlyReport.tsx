/**
 * `<MeiMonthlyReport/>` — "Relatório Mensal de Receitas Brutas" for the MEI (Res. CGSN 140/2018 art. 106, 108, 109 — Annex X):
 * the month's receipts split by activity (comércio / indústria / serviços) and by "com / sem documento fiscal". The MEI keeps
 * it (for the Fisco, on request) with the invoices attached; nothing is transmitted. Cash basis. Only meaningful for
 * `tax_regime = mei` — other regimes see a plain explanation instead of numbers.
 * `GET /api/finance/reports/mei-monthly` · `/exports/mei-monthly.{csv,pdf}`.
 */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { ACTIVITY_KINDS } from './types';
import { EmptyState, Field, FormError, HelpTip, Input, ListSkeleton, Notice, PageHeader, RefreshingBar, RetryError } from './controls';
import { formatCents, formatDate, monthStartIso } from './format';
import { FINANCE_EXPORT_PATHS, errorMessage, type FinanceHooks } from './hooks';
import { t } from './i18n';

export interface MeiMonthlyReportProps {
  hooks: FinanceHooks;
  canExport?: boolean;
  now?: Date;
}

export function MeiMonthlyReport({ hooks, canExport = false, now }: MeiMonthlyReportProps) {
  const base = React.useMemo(() => now ?? new Date(), [now]);
  const [month, setMonth] = React.useState(monthStartIso(base).slice(0, 7));
  const report = hooks.useMeiMonthly(`${month}-01`);
  const exp = hooks.useExport();

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
        {!d.applicable ? (
          <EmptyState message={t('mei.not_applicable')} />
        ) : (
          <>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-muted-foreground">
                  <th className="w-12 p-2">{t('mei.item')}</th>
                  <th className="p-2">{t('mei.description')}</th>
                  <th className="p-2 text-right">{t('mei.value')}</th>
                </tr>
              </thead>
              <tbody>
                {ACTIVITY_KINDS.map((kind) => {
                  const f = d.fields[kind];
                  const g = d.groups[kind];
                  return (
                    <React.Fragment key={kind}>
                      <tr className="bg-muted/50"><th colSpan={3} className="p-2 text-left text-xs">{f.title}</th></tr>
                      <tr className="border-b"><td className="p-2">{f.without_roman}</td><td className="p-2">{f.without}</td><td className="p-2 text-right">{formatCents(g.without_invoice_cents)}</td></tr>
                      <tr className="border-b"><td className="p-2">{f.with_roman}</td><td className="p-2">{f.with}</td><td className="p-2 text-right">{formatCents(g.with_invoice_cents)}</td></tr>
                      <tr className="border-b font-medium"><td className="p-2">{f.total_roman}</td><td className="p-2">{f.total}</td><td className="p-2 text-right">{formatCents(g.total_cents)}</td></tr>
                    </React.Fragment>
                  );
                })}
                <tr className="bg-muted font-semibold"><td className="p-2">{d.grand_total.roman}</td><td className="p-2">{d.grand_total.label}</td><td className="p-2 text-right">{formatCents(d.total_cents)}</td></tr>
              </tbody>
            </table>
            {d.unassigned_cents ? <p className="text-sm text-destructive">{t('mei.unassigned', { amount: formatCents(d.unassigned_cents) })}</p> : null}
            <p className="text-xs text-muted-foreground">{t('mei.deadline', { date: formatDate(d.deadline) })}</p>
            <p className="text-xs text-muted-foreground">{t('mei.basis', { law: d.legal_basis })}</p>
            <ul className="list-disc pl-5 text-xs text-muted-foreground">{d.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
            <Notice>{d.disclaimer}</Notice>
          </>
        )}
      </>
    );
  }

  const applicable = report.data?.applicable ?? false;
  return (
    <section className="space-y-3" aria-busy={report.isRefreshing}>
      <PageHeader
        title={t('mei.title')}
        subtitle={t('mei.subtitle')}
        actions={<HelpTip label={t('mei.help_label')}>{t('mei.help')}</HelpTip>}
      />
      <div className="max-w-xs">
        <Field label={t('mei.month')}><Input type="month" value={month} onChange={(e) => e.target.value && setMonth(e.target.value)} /></Field>
      </div>
      {canExport && applicable ? (
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" disabled={exp.isPending} onClick={() => exp.mutate({ path: FINANCE_EXPORT_PATHS.meiCsv, params: { month: `${month}-01` }, filename: `receitas-brutas-${month}.csv` })}>
            {t('exports.download_csv')}
          </Button>
          <Button size="sm" variant="outline" disabled={exp.isPending} onClick={() => exp.mutate({ path: FINANCE_EXPORT_PATHS.meiPdf, params: { month: `${month}-01` }, filename: `receitas-brutas-${month}.pdf` })}>
            {t('exports.download_pdf')}
          </Button>
        </div>
      ) : null}
      <FormError message={exp.error ? errorMessage(exp.error) : null} />
      <RefreshingBar active={report.isRefreshing} label={t('common.refreshing')} />
      {body}
    </section>
  );
}
