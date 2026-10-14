/**
 * `<DreReport/>` — Demonstração do Resultado do Exercício (CONTRACT §10 + §10.5 + §11; `GET /reports/dre`).
 *
 * `statement` rows in statement order with computed subtotals; each line expands into its category detail rows;
 * optional by-month columns; ZERO lines stay visible (greyed, with their help) so the owner learns the structure;
 * every line has plain-language help (the API's `help[key]`, else the built-in copy). A banner lists the server's
 * `warnings[]` and `accountant_alerts[]`. Money with no DRE line is shown in its own block and is NOT part of the
 * net result. MEI stores get the server title "DRE gerencial (MEI não é obrigado a ter DRE)". The toggle asks the
 * server for `view=managerial` (margem de contribuição), which answers a `managerial` block instead of `statement`.
 */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { Field, HelpTip, Input, ListSkeleton, Notice, PageHeader, RefreshingBar, RetryError } from './controls';
import type { DreDetailRow, DreLineHelp, DreManagerial, DreManagerialBlock, DreReportData, DreStatementItem, DreView } from './dreTypes';
import { formatCents, formatMonth, todayIso } from './format';
import { errorMessage, type FinanceHooks } from './hooks';
import { t } from './i18n';

export interface DreReportProps {
  hooks: FinanceHooks;
  now?: Date;
}

/** API help wins; otherwise the built-in plain-language copy for the key. */
export function helpFor(key: string, help: DreReportData['help'] | undefined): DreLineHelp {
  const h = help?.[key];
  if (h?.what) return h;
  return { what: t(`dre_help.${key}.what`), example: t(`dre_help.${key}.example`), source: t(`dre_help.${key}.source`) };
}

function LineHelp({ label, help }: { label: string; help: DreLineHelp }) {
  return (
    <HelpTip label={t('dre.help_for', { line: label })}>
      <span className="block">{help.what}</span>
      {help.example ? <span className="mt-1 block text-muted-foreground">{t('dre.example')}: {help.example}</span> : null}
      {help.source ? <span className="mt-1 block text-muted-foreground">{t('dre.source')}: {help.source}</span> : null}
    </HelpTip>
  );
}

function DetailRows({ rows, months, showMonths }: { rows: DreDetailRow[]; months: string[]; showMonths: boolean }) {
  return (
    <>
      {rows.map((d, i) => (
        <tr key={`${d.category_id ?? 'none'}-${i}`} className="border-b text-muted-foreground">
          <td className="py-1 pl-8 pr-2">{d.name}{d.behavior ? <span className="ml-1 text-xs">· {t(`behavior.${d.behavior}`)}</span> : null}</td>
          <td className="p-1 text-right">{formatCents(d.cents)}</td>
          {showMonths ? months.map((m) => <td key={m} className="p-1 text-right">{formatCents(d.by_month?.[m] ?? 0)}</td>) : null}
        </tr>
      ))}
    </>
  );
}

function StatementTable({ report, items }: { report: DreReportData; items: DreStatementItem[] }) {
  const [open, setOpen] = React.useState<Record<string, boolean>>({});
  const [showMonths, setShowMonths] = React.useState(false);
  const { months } = report;
  return (
    <div className="space-y-2">
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={showMonths} onChange={(e) => setShowMonths(e.target.checked)} /> {t('dre.by_month')}
      </label>
      <div className="overflow-x-auto">
        <table className="w-full text-sm" aria-label={t('dre.table')}>
          <thead>
            <tr className="border-b text-left text-xs text-muted-foreground">
              <th className="p-2">{t('dre.col_line')}</th>
              <th className="p-2 text-right">{t('report.total')}</th>
              {showMonths ? months.map((m) => <th key={m} className="p-2 text-right">{formatMonth(m)}</th>) : null}
            </tr>
          </thead>
          <tbody>
            {items.map((l) => {
              const subtotal = l.kind === 'subtotal';
              const zero = !subtotal && (l.empty || l.cents === 0);
              const expandable = l.detail.length > 0;
              const expanded = !!open[l.key];
              return (
                <React.Fragment key={l.key}>
                  <tr
                    data-line={l.key}
                    data-zero={zero ? 'true' : undefined}
                    className={`border-b ${subtotal ? 'bg-muted/50 font-semibold' : ''} ${zero ? 'text-muted-foreground' : ''}`}
                  >
                    <td className="p-2">
                      {expandable ? (
                        <button
                          type="button"
                          className="mr-1 inline-block w-4 text-xs"
                          aria-expanded={expanded}
                          aria-label={t('dre.toggle_details', { line: l.label })}
                          onClick={() => setOpen((s) => ({ ...s, [l.key]: !s[l.key] }))}
                        >
                          {expanded ? '▾' : '▸'}
                        </button>
                      ) : null}
                      {l.label}
                      <LineHelp label={l.label} help={helpFor(l.key, report.help)} />
                      {zero ? <span className="ml-2 text-xs italic">{t('dre.zero_line')}</span> : null}
                    </td>
                    <td className="p-2 text-right whitespace-nowrap">{formatCents(l.cents)}</td>
                    {showMonths ? months.map((m) => <td key={m} className="p-2 text-right whitespace-nowrap">{formatCents(l.by_month?.[m] ?? 0)}</td>) : null}
                  </tr>
                  {expanded ? <DetailRows rows={l.detail} months={months} showMonths={showMonths} /> : null}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Unclassified({ report }: { report: DreReportData }) {
  const u = report.unclassified;
  if (!u || (u.net_cents === 0 && u.detail.length === 0)) return null;
  return (
    <section className="space-y-1 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm" aria-label={t('dre.unclassified_title')}>
      <h3 className="font-semibold">
        {t('dre.unclassified_title')}: {formatCents(u.net_cents)}
        <LineHelp label={t('dre.unclassified_title')} help={helpFor('unclassified', report.help)} />
      </h3>
      <p className="text-xs">{t('dre.unclassified_note')}</p>
      <table className="w-full">
        <tbody>
          <DetailRows rows={u.detail} months={report.months} showMonths={false} />
        </tbody>
      </table>
    </section>
  );
}

const MANAGERIAL_SECTIONS: { key: keyof Pick<DreManagerial, 'revenue' | 'variable_costs' | 'contribution_margin' | 'fixed_costs' | 'other_income' | 'net_result'>; sign: string; subtotal: boolean }[] = [
  { key: 'revenue', sign: '', subtotal: false },
  { key: 'variable_costs', sign: '(−) ', subtotal: false },
  { key: 'contribution_margin', sign: '= ', subtotal: true },
  { key: 'fixed_costs', sign: '(−) ', subtotal: false },
  { key: 'other_income', sign: '(+) ', subtotal: false },
  { key: 'net_result', sign: '= ', subtotal: true },
];

function ManagerialTable({ m }: { m: DreManagerial }) {
  const [open, setOpen] = React.useState<Record<string, boolean>>({});
  return (
    <div className="space-y-2">
      <p className="text-sm" role="status">
        {t('dre.contribution_margin')}: <strong>{formatCents(m.contribution_margin.cents)}</strong>
        {m.contribution_margin.percent_of_revenue_bps != null ? ` (${(m.contribution_margin.percent_of_revenue_bps / 100).toFixed(1).replace('.', ',')}%)` : ''}
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm" aria-label={t('dre.table_managerial')}>
          <thead>
            <tr className="border-b text-left text-xs text-muted-foreground">
              <th className="p-2">{t('dre.col_line')}</th>
              <th className="p-2 text-right">{t('report.total')}</th>
            </tr>
          </thead>
          <tbody>
            {MANAGERIAL_SECTIONS.map(({ key, sign, subtotal }) => {
              const block: DreManagerialBlock = m[key];
              const label = t(`dre_managerial.${key}`);
              const detail = block.detail ?? [];
              const zero = !subtotal && block.cents === 0;
              return (
                <React.Fragment key={key}>
                  <tr data-line={key} data-zero={zero ? 'true' : undefined} className={`border-b ${subtotal ? 'bg-muted/50 font-semibold' : ''} ${zero ? 'text-muted-foreground' : ''}`}>
                    <td className="p-2">
                      {detail.length > 0 ? (
                        <button type="button" className="mr-1 inline-block w-4 text-xs" aria-expanded={!!open[key]} aria-label={t('dre.toggle_details', { line: label })} onClick={() => setOpen((s) => ({ ...s, [key]: !s[key] }))}>
                          {open[key] ? '▾' : '▸'}
                        </button>
                      ) : null}
                      {sign}{label}
                      <HelpTip label={t('dre.help_for', { line: label })}>{t(`dre_managerial_help.${key}`)}</HelpTip>
                      {zero ? <span className="ml-2 text-xs italic">{t('dre.zero_line')}</span> : null}
                    </td>
                    <td className="p-2 text-right whitespace-nowrap">{formatCents(block.cents)}</td>
                  </tr>
                  {open[key]
                    ? detail.map((d, i) => (
                        <tr key={`${d.category_id ?? 'x'}-${i}`} className="border-b text-muted-foreground">
                          <td className="py-1 pl-8 pr-2">{d.name}</td>
                          <td className="p-1 text-right">{formatCents(d.cents)}</td>
                        </tr>
                      ))
                    : null}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted-foreground">{t('dre.managerial_help')}</p>
    </div>
  );
}

function Banner({ report }: { report: DreReportData }) {
  const warnings = report.warnings ?? [];
  const alerts = report.accountant_alerts ?? [];
  if (!warnings.length && !alerts.length) return null;
  return (
    <div className="space-y-2" aria-label={t('dre.warnings')}>
      {warnings.map((w) => (
        <Notice key={w.code} tone={w.severity === 'critical' ? 'critical' : w.severity === 'warning' ? 'warning' : 'info'}>
          <span data-warning={w.code}>{w.message}</span>
          {w.action ? <span className="mt-0.5 block text-xs">{t('dre.what_to_do')}: {w.action}</span> : null}
        </Notice>
      ))}
      {alerts.length ? (
        <Notice tone="warning" role="note">
          <strong>{t('dre.accountant_alerts')}</strong>
          <ul className="list-disc pl-5">
            {alerts.map((a) => (
              <li key={a.code}>
                {a.message}
                {a.why ? <span className="text-xs"> — {a.why}</span> : null}
                {a.source ? <span className="block text-xs text-muted-foreground">{t('dre.source')}: {a.source}</span> : null}
              </li>
            ))}
          </ul>
        </Notice>
      ) : null}
    </div>
  );
}

export function DreReport({ hooks, now }: DreReportProps) {
  const base = React.useMemo(() => now ?? new Date(), [now]);
  const [from, setFrom] = React.useState(`${base.getFullYear()}-01-01`);
  const [to, setTo] = React.useState(todayIso(base));
  const [view, setView] = React.useState<DreView>('statement');
  const report = hooks.useDre({ from, to, view });

  const data = report.data;
  const managerial = view === 'managerial';
  const title = data ? (data.tax_regime === 'mei' ? data.title : managerial && data.managerial?.title ? data.managerial.title : data.title) : t('dre.title');

  let body: React.ReactNode;
  if (report.showSkeleton) body = <ListSkeleton rows={8} />;
  else if (report.isError && !data) {
    body = <RetryError message={`${t('common.error_loading')}: ${errorMessage(report.error)}`} onRetry={() => report.refetch()} retryLabel={t('common.retry')} />;
  } else if (data) {
    body = (
      <>
        <Banner report={data} />
        {managerial ? (
          data.managerial ? <ManagerialTable m={data.managerial} /> : <Notice>{t('dre.managerial_unavailable')}</Notice>
        ) : data.statement ? (
          <StatementTable report={data} items={data.statement} />
        ) : (
          <Notice>{t('dre.managerial_unavailable')}</Notice>
        )}
        <Unclassified report={data} />
      </>
    );
  }

  return (
    <section className="space-y-3" aria-busy={report.isRefreshing}>
      <PageHeader title={title} subtitle={t('dre.subtitle')} />
      <div className="flex flex-wrap items-end gap-3">
        <Field label={t('report.from')}><Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></Field>
        <Field label={t('report.to')}><Input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></Field>
        <div role="group" aria-label={t('dre.view')} className="flex gap-1">
          <Button size="sm" variant={managerial ? 'outline' : 'primary'} aria-pressed={!managerial} onClick={() => setView('statement')}>{t('dre.view_accounting')}</Button>
          <Button size="sm" variant={managerial ? 'primary' : 'outline'} aria-pressed={managerial} onClick={() => setView('managerial')}>{t('dre.view_managerial')}</Button>
        </div>
      </div>
      <RefreshingBar active={report.isRefreshing} label={t('common.refreshing')} />
      {body}
    </section>
  );
}
