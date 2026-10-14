/**
 * `<LivroCaixaReport/>` — "Livro Caixa": the cash book an ME/EPP keeps (data, histórico, entrada, saída, saldo) over every
 * account, with CSV and PDF downloads. A VIEW over the ledger — transfers between your own accounts are not income or
 * expense and are left out. Prepared by the system; the contador keeps the official book (LC 123/2006 art. 26 §2,
 * Res. CGSN 140/2018 art. 63). `GET /api/finance/reports/livro-caixa` · `/exports/livro-caixa.{csv,pdf}`.
 */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { EmptyState, Field, FormError, HelpTip, Input, ListSkeleton, Notice, PageHeader, Pager, RefreshingBar, RetryError } from './controls';
import { formatCents, formatDate, monthStartIso, todayIso } from './format';
import { FINANCE_EXPORT_PATHS, errorMessage, type FinanceHooks } from './hooks';
import { t } from './i18n';

export interface LivroCaixaReportProps {
  hooks: FinanceHooks;
  /** UX only: whether the downloads are offered (admin or the accountant read grant). The server enforces it. */
  canExport?: boolean;
  now?: Date;
}

const PAGE_SIZE = 100;

export function LivroCaixaReport({ hooks, canExport = false, now }: LivroCaixaReportProps) {
  const base = React.useMemo(() => now ?? new Date(), [now]);
  const [from, setFrom] = React.useState(monthStartIso(base));
  const [to, setTo] = React.useState(todayIso(base));
  const [page, setPage] = React.useState(1);
  const book = hooks.useLivroCaixa({ from, to, page, page_size: PAGE_SIZE });
  const exp = hooks.useExport();

  let body: React.ReactNode;
  if (book.showSkeleton) body = <ListSkeleton rows={6} />;
  else if (book.isError && !book.data) {
    body = <RetryError message={`${t('common.error_loading')}: ${errorMessage(book.error)}`} onRetry={() => book.refetch()} retryLabel={t('common.retry')} />;
  } else if (book.data) {
    const d = book.data;
    const pages = Math.max(1, Math.ceil(d.row_count / d.page_size));
    body = (
      <>
        <dl className="grid gap-2 text-sm sm:grid-cols-4">
          <div className="rounded-md border p-2"><dt>{t('livro.opening')}</dt><dd>{formatCents(d.opening_balance_cents)}</dd></div>
          <div className="rounded-md border p-2"><dt>{t('livro.total_in')}</dt><dd>{formatCents(d.total_in_cents)}</dd></div>
          <div className="rounded-md border p-2"><dt>{t('livro.total_out')}</dt><dd>{formatCents(d.total_out_cents)}</dd></div>
          <div className="rounded-md border bg-muted p-2 font-semibold"><dt>{t('livro.closing')}</dt><dd>{formatCents(d.closing_balance_cents)}</dd></div>
        </dl>
        {d.rows.length === 0 ? (
          <EmptyState message={t('livro.empty')} />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th className="p-2">{t('livro.date')}</th>
                <th className="p-2">{t('livro.history')}</th>
                <th className="p-2">{t('livro.account')}</th>
                <th className="p-2 text-right">{t('livro.in')}</th>
                <th className="p-2 text-right">{t('livro.out')}</th>
                <th className="p-2 text-right">{t('livro.balance')}</th>
              </tr>
            </thead>
            <tbody>
              {d.rows.map((r, i) => (
                <tr key={r.ledger_id ?? `${r.on}-${i}`} className="border-b">
                  <td className="p-2 whitespace-nowrap">{formatDate(r.on)}</td>
                  <td className="p-2">
                    {r.history}
                    {r.counterparty ? <span className="block text-xs text-muted-foreground">{r.counterparty}</span> : null}
                  </td>
                  <td className="p-2 text-xs">{r.account ?? '—'}</td>
                  <td className="p-2 text-right">{r.in ? formatCents(r.in) : ''}</td>
                  <td className="p-2 text-right">{r.out ? formatCents(r.out) : ''}</td>
                  <td className="p-2 text-right font-medium">{formatCents(r.balance_cents)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <Pager page={d.page} totalPages={pages} onPage={setPage} />
        <p className="text-xs text-muted-foreground">{t('livro.basis', { law: d.legal_basis })}</p>
        <ul className="list-disc pl-5 text-xs text-muted-foreground">{d.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
        <Notice>{d.disclaimer}</Notice>
      </>
    );
  }

  return (
    <section className="space-y-3" aria-busy={book.isRefreshing}>
      <PageHeader
        title={t('livro.title')}
        subtitle={t('livro.subtitle')}
        actions={<HelpTip label={t('livro.help_label')}>{t('livro.help')}</HelpTip>}
      />
      <div className="grid max-w-md gap-2 sm:grid-cols-2">
        <Field label={t('report.from')}><Input type="date" value={from} onChange={(e) => { setFrom(e.target.value); setPage(1); }} /></Field>
        <Field label={t('report.to')}><Input type="date" value={to} onChange={(e) => { setTo(e.target.value); setPage(1); }} /></Field>
      </div>
      {canExport ? (
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" disabled={exp.isPending} onClick={() => exp.mutate({ path: FINANCE_EXPORT_PATHS.livroCaixaCsv, params: { from, to }, filename: 'livro-caixa.csv' })}>
            {t('exports.download_csv')}
          </Button>
          <Button size="sm" variant="outline" disabled={exp.isPending} onClick={() => exp.mutate({ path: FINANCE_EXPORT_PATHS.livroCaixaPdf, params: { from, to }, filename: 'livro-caixa.pdf' })}>
            {t('exports.download_pdf')}
          </Button>
        </div>
      ) : null}
      <FormError message={exp.error ? errorMessage(exp.error) : null} />
      <RefreshingBar active={book.isRefreshing} label={t('common.refreshing')} />
      {body}
    </section>
  );
}
