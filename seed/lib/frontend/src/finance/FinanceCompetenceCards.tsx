/**
 * `<RevenueByCategoryCard/>` + `<CompetenceResultCard/>` — the two competence-basis cards of the finance overview
 * ("De onde veio a receita do mês" and "Resultado do mês (competência)"), both derived from ONE `GET /reports/dre`
 * answer for the month (no second source of truth). Opt-in through `competenceCards` on the overview/shell.
 *
 * Honesty rules: tax is NEVER estimated. The tax line shows the DRE's own `deductions` line only when the tax
 * regime is informed and that line carries booked money; otherwise it reads "depende do contador" and the result
 * is "—". While loading: skeleton (never an empty state); on failure: a visible, retryable error.
 */
import * as React from 'react';
import { ChartCard } from '../design-system/charts/ChartCard';
import { Button } from '../design-system/ui/Button';
import type { DreReportData, DreStatementItem } from './dreTypes';
import { formatCents } from './format';
import { t } from './i18n';

const SERIES = ['--chart-1', '--chart-2', '--chart-3', '--chart-4'] as const;

const line = (r: DreReportData | undefined, key: string): DreStatementItem | undefined => r?.statement?.find((l) => l.key === key);

export interface CompetenceCardProps {
  report: DreReportData | undefined;
  loading: boolean;
  error: string | null;
  onRetry?: () => void;
}

/** Pure: the revenue split by category (largest first, tail grouped), derived from the DRE `gross_revenue` detail. */
export function revenueSlices(report: DreReportData | undefined): { name: string; cents: number }[] {
  const rows = (line(report, 'gross_revenue')?.detail ?? []).filter((d) => d.cents > 0).sort((a, b) => b.cents - a.cents);
  const head = rows.length <= SERIES.length ? rows : rows.slice(0, SERIES.length - 1);
  const tail = rows.slice(head.length);
  const out = head.map((d) => ({ name: d.name || t('competence.revenue_uncategorized'), cents: d.cents }));
  if (tail.length > 0) out.push({ name: t('competence.revenue_other'), cents: tail.reduce((s, d) => s + d.cents, 0) });
  return out;
}

export function RevenueByCategoryCard({ report, loading, error, onRetry }: CompetenceCardProps) {
  const slices = revenueSlices(report);
  const total = slices.reduce((s, x) => s + x.cents, 0);
  const pct = (c: number) => Math.round((c / total) * 100);
  const summary = slices.map((x) => `${x.name} ${pct(x.cents)}%`).join(', ');
  return (
    <ChartCard
      title={t('competence.revenue_title')}
      loading={loading}
      error={error}
      isEmpty={!loading && !error && total === 0}
      emptyMessage={t('competence.revenue_empty')}
      actions={error && onRetry ? <Button size="sm" variant="outline" onClick={onRetry}>{t('common.retry')}</Button> : undefined}
    >
      <div className="flex h-2 overflow-hidden rounded-full bg-muted" role="img" aria-label={summary}>
        {slices.map((x, i) => (
          <span key={x.name} style={{ width: `${(x.cents / total) * 100}%`, background: `hsl(var(${SERIES[i % SERIES.length]}))` }} />
        ))}
      </div>
      <ul className="mt-2 space-y-1 text-sm">
        {slices.map((x, i) => (
          <li key={x.name} className="grid grid-cols-[10px_1fr_auto] items-center gap-2">
            <i className="block h-2.5 w-2.5 rounded-sm" style={{ background: `hsl(var(${SERIES[i % SERIES.length]}))` }} aria-hidden="true" />
            <span>{x.name}</span>
            <span className="tabular-nums">{formatCents(x.cents)}</span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-muted-foreground">{t('competence.revenue_hint')}</p>
    </ChartCard>
  );
}

export function CompetenceResultCard({ report, loading, error, onRetry, onSeeDre }: CompetenceCardProps & { onSeeDre?: () => void }) {
  const gross = line(report, 'gross_revenue');
  const taxes = line(report, 'deductions');
  const costs = line(report, 'cost_of_sales');
  const expenseCents = ['selling_expenses', 'administrative_expenses', 'other_operating'].reduce((s, k) => s + (line(report, k)?.cents ?? 0), 0);
  const taxKnown = !!report && report.tax_regime !== 'unknown' && (taxes?.cents ?? 0) > 0;
  const result = taxKnown ? report.net_result_cents : undefined;
  return (
    <ChartCard
      title={t('competence.result_title')}
      loading={loading}
      error={error}
      actions={
        error && onRetry ? (
          <Button size="sm" variant="outline" onClick={onRetry}>{t('common.retry')}</Button>
        ) : onSeeDre ? (
          <Button size="sm" variant="ghost" onClick={onSeeDre}>{t('competence.see_dre')}</Button>
        ) : undefined
      }
    >
      <dl className="space-y-1 text-sm">
        <div className="flex justify-between gap-3"><dt>{t('competence.gross_revenue')}</dt><dd className="tabular-nums">{formatCents(gross?.cents ?? 0)}</dd></div>
        <div className="flex justify-between gap-3">
          <dt>{t('competence.taxes')}</dt>
          <dd className="tabular-nums">
            {taxKnown ? formatCents(-(taxes?.cents ?? 0)) : <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-xs">{t('competence.tax_pending')}</span>}
          </dd>
        </div>
        <div className="flex justify-between gap-3"><dt>{t('competence.costs')}</dt><dd className="tabular-nums">{formatCents(-(costs?.cents ?? 0))}</dd></div>
        <div className="flex justify-between gap-3"><dt>{t('competence.expenses')}</dt><dd className="tabular-nums">{formatCents(-expenseCents)}</dd></div>
        <div className="flex justify-between gap-3 font-semibold"><dt>{t('competence.result')}</dt><dd className="tabular-nums">{result === undefined ? '—' : formatCents(result)}</dd></div>
      </dl>
      {taxKnown ? null : <p className="mt-2 text-xs text-muted-foreground">{t('competence.result_hint')}</p>}
    </ChartCard>
  );
}
