/**
 * `<BudgetPage/>` — "Orçamento": the planned amount per category and month beside what actually happened.
 * The realizado is the DRE's own number (competência, no cancelled, no transfers), so this screen and the DRE never
 * disagree. Admins type the planned amount straight into the grid and save once; the accountant (read grant) sees it
 * read-only. Over-budget expenses and under-target income are flagged in words, not only colour.
 * `GET /api/finance/reports/budget` · `PUT /api/finance/budgets` · `DELETE /api/finance/budgets/{id}`.
 */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import type { BudgetCell, BudgetItemInput, BudgetRow, BudgetStatus } from './accountantTypes';
import { EmptyState, Field, FormError, HelpTip, Input, ListSkeleton, Notice, PageHeader, RefreshingBar, RetryError, Select } from './controls';
import { centsToInput, formatCents, formatMonth, parseMoneyToCents } from './format';
import { errorMessage, type FinanceHooks } from './hooks';
import { t } from './i18n';

export interface BudgetPageProps {
  hooks: FinanceHooks;
  /** UX only: the server enforces the admin gate on every write. */
  isAdmin?: boolean;
  now?: Date;
}

const STATUS_TONE: Record<BudgetStatus, string> = {
  ok: 'text-foreground',
  over: 'text-destructive font-medium',
  under: 'text-amber-700 font-medium',
  no_budget: 'text-muted-foreground',
};

function CellView({ cell }: { cell: BudgetCell }) {
  return (
    <div className="space-y-0.5 text-right text-xs">
      <div>{formatCents(cell.actual_cents)}</div>
      {cell.status !== 'no_budget' ? (
        <div className={STATUS_TONE[cell.status]}>
          {cell.variance_cents === 0 ? t('budget.on_plan') : `${cell.variance_cents > 0 ? '+' : '−'} ${formatCents(Math.abs(cell.variance_cents))}`}
          {cell.status === 'over' ? ` · ${t('budget.status_over')}` : cell.status === 'under' ? ` · ${t('budget.status_under')}` : ''}
        </div>
      ) : null}
    </div>
  );
}

export function BudgetPage({ hooks, isAdmin = false, now }: BudgetPageProps) {
  const base = React.useMemo(() => now ?? new Date(), [now]);
  const year = base.getFullYear();
  const [from, setFrom] = React.useState(`${year}-01-01`);
  const [to, setTo] = React.useState(`${year}-12-31`);
  const report = hooks.useBudgetReport({ from, to });
  const budgets = hooks.useBudgets({ from, to });
  const categories = hooks.useCategories();
  const m = hooks.useBudgetMutations();

  /** `${category_id}|${YYYY-MM}` → the text typed in that cell (only cells the admin touched). */
  const [edits, setEdits] = React.useState<Record<string, string>>({});
  const [extraRows, setExtraRows] = React.useState<string[]>([]);
  const [cellErrors, setCellErrors] = React.useState<Record<string, string>>({});
  const [saved, setSaved] = React.useState(false);

  const existing = React.useMemo(() => {
    const out = new Map<string, { id: string; amount_cents: number }>();
    for (const b of budgets.data ?? []) out.set(`${b.category_id}|${b.month.slice(0, 7)}`, { id: b.id, amount_cents: b.amount_cents });
    return out;
  }, [budgets.data]);

  const data = report.data;
  const catById = React.useMemo(() => new Map((categories.data ?? []).map((c) => [c.id, c])), [categories.data]);
  const rows: BudgetRow[] = React.useMemo(() => {
    const out = [...(data?.rows ?? [])];
    for (const id of extraRows) {
      const c = catById.get(id);
      if (!c || out.some((r) => r.category_id === id)) continue;
      out.push({ category_id: id, name: c.name, path: c.name, direction: c.direction, months: {}, total: { budget_cents: 0, actual_cents: 0, variance_cents: 0, status: 'no_budget' } });
    }
    return out;
  }, [data, extraRows, catById]);

  function cellKey(row: BudgetRow, month: string) {
    return `${row.category_id}|${month}`;
  }
  function valueOf(row: BudgetRow, month: string): string {
    const k = cellKey(row, month);
    if (k in edits) return edits[k];
    const ex = existing.get(k);
    return ex ? centsToInput(ex.amount_cents) : '';
  }

  async function save() {
    setSaved(false);
    const items: BudgetItemInput[] = [];
    const removals: string[] = [];
    const errs: Record<string, string> = {};
    for (const [k, text] of Object.entries(edits)) {
      const [categoryId, month] = k.split('|');
      const prior = existing.get(k);
      if (text.trim() === '') {
        if (prior) removals.push(prior.id);
        continue;
      }
      const cents = parseMoneyToCents(text);
      if (cents === null || cents < 0) {
        errs[k] = t('budget.amount_invalid');
        continue;
      }
      if (prior && prior.amount_cents === cents) continue;
      items.push({ category_id: categoryId, month: `${month}-01`, amount_cents: cents });
    }
    setCellErrors(errs);
    if (Object.keys(errs).length) return;
    try {
      if (items.length) await m.save.mutateAsync(items);
      for (const id of removals) await m.remove.mutateAsync(id);
      setEdits({});
      setSaved(true);
    } catch {
      // Surfaced through the mutation error below.
    }
  }

  let body: React.ReactNode;
  if (report.showSkeleton) body = <ListSkeleton rows={6} />;
  else if (report.isError && !data) {
    body = <RetryError message={`${t('common.error_loading')}: ${errorMessage(report.error)}`} onRetry={() => report.refetch()} retryLabel={t('common.retry')} />;
  } else if (data) {
    const dirty = Object.keys(edits).length > 0;
    const addable = (categories.data ?? []).filter((c) => c.active && c.direction !== 'transfer' && !rows.some((r) => r.category_id === c.id));
    body = (
      <>
        {data.warnings.map((w) => (
          <Notice key={w.code} tone={w.severity === 'critical' ? 'critical' : w.severity === 'warning' ? 'warning' : 'info'}>
            <span data-warning={w.code}>{w.message}</span>
            {w.action ? <span className="mt-0.5 block text-xs">{t('dre.what_to_do')}: {w.action}</span> : null}
          </Notice>
        ))}
        <dl className="grid gap-2 text-sm sm:grid-cols-3">
          <div className="rounded-md border p-2">
            <dt>{t('budget.income')}</dt>
            <dd className="text-xs">{t('budget.planned')}: {formatCents(data.income.budget_cents)} · {t('budget.actual')}: {formatCents(data.income.actual_cents)}</dd>
          </div>
          <div className="rounded-md border p-2">
            <dt>{t('budget.expense')}</dt>
            <dd className="text-xs">{t('budget.planned')}: {formatCents(data.expense.budget_cents)} · {t('budget.actual')}: {formatCents(data.expense.actual_cents)}</dd>
          </div>
          <div className="rounded-md border bg-muted p-2 font-semibold">
            <dt>{t('budget.result')}</dt>
            <dd className="text-xs">{t('budget.planned')}: {formatCents(data.result.budget_cents)} · {t('budget.actual')}: {formatCents(data.result.actual_cents)}</dd>
          </div>
        </dl>
        {rows.length === 0 ? (
          <EmptyState message={t('budget.empty')} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-muted-foreground">
                  <th className="p-2">{t('budget.category')}</th>
                  {data.months.map((mo) => <th key={mo} className="p-2 text-right">{formatMonth(mo)}</th>)}
                  <th className="p-2 text-right">{t('budget.total')}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.category_id} className="border-b align-top" data-row={row.name}>
                    <td className="p-2">
                      {row.path}
                      <span className="ml-1 text-xs text-muted-foreground">({t(`category_direction.${row.direction}`)})</span>
                    </td>
                    {data.months.map((mo) => {
                      const cell = row.months[mo];
                      const k = cellKey(row, mo);
                      return (
                        <td key={mo} className="p-2">
                          {isAdmin ? (
                            <>
                              <Input
                                aria-label={`${t('budget.planned')}: ${row.name} ${formatMonth(mo)}`}
                                inputMode="decimal"
                                placeholder="0,00"
                                value={valueOf(row, mo)}
                                onChange={(e) => setEdits((prev) => ({ ...prev, [k]: e.target.value }))}
                                className="h-7 text-right text-xs"
                              />
                              {cellErrors[k] ? <span className="block text-xs text-destructive">{cellErrors[k]}</span> : null}
                            </>
                          ) : cell && cell.status !== 'no_budget' ? (
                            <div className="text-right text-xs text-muted-foreground">{t('budget.planned')}: {formatCents(cell.budget_cents)}</div>
                          ) : null}
                          {cell ? <CellView cell={cell} /> : null}
                        </td>
                      );
                    })}
                    <td className="p-2"><CellView cell={row.total} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {isAdmin ? (
          <div className="flex flex-wrap items-end gap-3">
            <Field label={t('budget.add_category')}>
              <Select value="" onChange={(e) => { if (e.target.value) setExtraRows((prev) => [...prev, e.target.value]); }}>
                <option value="">{t('budget.choose_category')}</option>
                {addable.map((c) => <option key={c.id} value={c.id}>{c.name} ({t(`category_direction.${c.direction}`)})</option>)}
              </Select>
            </Field>
            <Button onClick={() => void save()} disabled={!dirty || m.save.isPending || m.remove.isPending}>
              {m.save.isPending || m.remove.isPending ? t('common.saving') : t('budget.save')}
            </Button>
            {saved ? <span role="status" className="text-sm text-muted-foreground">{t('common.saved')}</span> : null}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">{t('budget.read_only')}</p>
        )}
        <ul className="list-disc pl-5 text-xs text-muted-foreground">{data.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
      </>
    );
  }

  const mutErr = m.save.error ?? m.remove.error;
  return (
    <section className="space-y-3" aria-busy={report.isRefreshing}>
      <PageHeader
        title={t('budget.title')}
        subtitle={t('budget.subtitle')}
        actions={<HelpTip label={t('budget.help_label')}>{t('budget.help')}</HelpTip>}
      />
      <div className="grid max-w-md gap-2 sm:grid-cols-2">
        <Field label={t('report.from')}><Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></Field>
        <Field label={t('report.to')}><Input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></Field>
      </div>
      <RefreshingBar active={report.isRefreshing} label={t('common.refreshing')} />
      <FormError message={mutErr ? errorMessage(mutErr) : null} />
      {body}
    </section>
  );
}
