/**
 * `<FinanceCategoryManager/>` — hierarchical chart of categories (income / expense / transfer) with the
 * two columns that drive the DRE: **Linha do DRE** and **Comportamento** (variável / fixo). Mapping a
 * category is a data edit (`PATCH /categories/{id}`), never code — so the contador can change it.
 * Named `FinanceCategoryManager` because `CategoryManager` is the commerce catalog organ.
 */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { ConfirmButton, EmptyState, Field, FormError, HelpTip, Input, ListSkeleton, PageHeader, RefreshingBar, RetryError, Select } from './controls';
import { errorMessage, type FinanceHooks } from './hooks';
import { t } from './i18n';
import type { DreAssignableLine, DreLine } from './dreTypes';
import { ACTIVITY_KINDS, CATEGORY_BEHAVIORS, CATEGORY_DIRECTIONS, type ActivityKind, type CategoryBehavior, type CategoryDirection, type FinanceCategory } from './types';

/** Which DRE lines make sense per category direction (dre-structure.md §2a). */
export const DRE_LINES_BY_DIRECTION: Record<CategoryDirection, readonly DreAssignableLine[]> = {
  income: ['gross_revenue', 'other_operating', 'financial_revenue'],
  expense: ['deductions', 'cost_of_sales', 'selling_expenses', 'administrative_expenses', 'other_operating', 'financial_expenses', 'income_taxes'],
  transfer: [],
};

export interface FinanceCategoryManagerProps {
  hooks: FinanceHooks;
  isAdmin?: boolean;
}

interface Row {
  cat: FinanceCategory;
  depth: number;
}

/** Depth-first flatten: roots by direction then name, children under their parent. */
export function flattenCategories(list: FinanceCategory[]): Row[] {
  const byParent = new Map<string | null, FinanceCategory[]>();
  const ids = new Set(list.map((c) => c.id));
  for (const c of list) {
    const key = c.parent_id && ids.has(c.parent_id) ? c.parent_id : null;
    byParent.set(key, [...(byParent.get(key) ?? []), c]);
  }
  const order = (a: FinanceCategory, b: FinanceCategory) =>
    CATEGORY_DIRECTIONS.indexOf(a.direction) - CATEGORY_DIRECTIONS.indexOf(b.direction) || a.name.localeCompare(b.name, 'pt-BR');
  const out: Row[] = [];
  const walk = (parent: string | null, depth: number) => {
    for (const c of [...(byParent.get(parent) ?? [])].sort(order)) {
      out.push({ cat: c, depth });
      walk(c.id, depth + 1);
    }
  };
  walk(null, 0);
  return out;
}

export function FinanceCategoryManager({ hooks, isAdmin = false }: FinanceCategoryManagerProps) {
  const cats = hooks.useCategories();
  const m = hooks.useCategoryMutations();

  const [editing, setEditing] = React.useState<FinanceCategory | 'new' | null>(null);
  const [name, setName] = React.useState('');
  const [direction, setDirection] = React.useState<CategoryDirection>('expense');
  const [parent, setParent] = React.useState('');
  const [dreLine, setDreLine] = React.useState('');
  const [behavior, setBehavior] = React.useState('');
  const [isDas, setIsDas] = React.useState(false);
  const [accountingCode, setAccountingCode] = React.useState('');
  const [activityKind, setActivityKind] = React.useState('');
  const [nameError, setNameError] = React.useState<string | null>(null);

  function open(c: FinanceCategory | null) {
    setEditing(c ?? 'new');
    setName(c?.name ?? '');
    setDirection(c?.direction ?? 'expense');
    setParent(c?.parent_id ?? '');
    setDreLine(c?.dre_line ?? '');
    setBehavior(c?.behavior ?? '');
    setIsDas(c?.is_das ?? false);
    setAccountingCode(c?.accounting_code ?? '');
    setActivityKind(c?.activity_kind ?? '');
    setNameError(null);
  }

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    if (!name.trim()) {
      setNameError(t('common.required'));
      return;
    }
    setNameError(null);
    const formDirection = editing && editing !== 'new' ? editing.direction : direction;
    const mapping = formDirection === 'transfer'
      ? {}
      : {
          dre_line: (dreLine || null) as DreLine | null,
          behavior: (behavior || null) as CategoryBehavior | null,
          is_das: formDirection === 'expense' ? isDas : false,
          // Sent when set, or when clearing a previous value (an untouched empty field stays out of the body).
          ...(accountingCode.trim() || (editing && editing !== 'new' && editing.accounting_code) ? { accounting_code: accountingCode.trim() || null } : {}),
          ...(formDirection === 'income' ? { activity_kind: (activityKind || null) as ActivityKind | null } : {}),
        };
    try {
      if (editing === 'new') await m.create.mutateAsync({ name: name.trim(), direction, parent_id: parent || null, ...mapping });
      else if (editing) await m.update.mutateAsync({ id: editing.id, name: name.trim(), parent_id: parent || null, ...mapping });
      setEditing(null);
    } catch {
      // Surfaced below.
    }
  }

  if (cats.showSkeleton) return <ListSkeleton />;
  if (cats.isError && !cats.data) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(cats.error)}`} onRetry={() => cats.refetch()} retryLabel={t('common.retry')} />;
  }
  const list = cats.data ?? [];
  const rows = flattenCategories(list);
  const mutErr = m.create.error ?? m.update.error ?? m.remove.error;
  const formDirection = editing && editing !== 'new' ? editing.direction : direction;
  const parentOptions = list.filter((c) => c.direction === formDirection && (editing === 'new' || editing === null || c.id !== editing.id));
  const unmapped = list.filter((c) => c.active && c.direction !== 'transfer' && !c.dre_line).length;

  return (
    <section className="space-y-3" aria-busy={cats.isRefreshing}>
      <PageHeader
        title={t('categories.title')}
        subtitle={t('categories.subtitle')}
        actions={isAdmin ? <Button size="sm" onClick={() => open(null)}>{t('categories.add')}</Button> : undefined}
      />
      <RefreshingBar active={cats.isRefreshing} label={t('common.refreshing')} />
      <FormError message={mutErr ? errorMessage(mutErr) : null} />
      {unmapped > 0 ? (
        <p role="status" className="text-xs text-amber-700">{t('categories.unmapped', { n: unmapped })}</p>
      ) : null}
      {rows.length === 0 && editing === null ? <EmptyState message={t('categories.empty')} /> : null}
      {rows.length > 0 ? (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-xs text-muted-foreground">
              <th className="p-2">{t('categories.name')}</th>
              <th className="p-2">{t('categories.direction')}</th>
              <th className="p-2">{t('categories.dre_line')}</th>
              <th className="p-2">{t('categories.behavior')}</th>
              <th className="p-2">{t('categories.accounting_code')}</th>
              <th className="p-2"><span className="sr-only">{t('common.actions')}</span></th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ cat: c, depth }) => {
              const lines = DRE_LINES_BY_DIRECTION[c.direction];
              return (
                <tr key={c.id} className={c.active ? 'border-b' : 'border-b text-muted-foreground'}>
                  <td className="p-2" style={{ paddingLeft: `${0.5 + depth * 1.25}rem` }}>
                    {c.name}
                    {c.is_das ? <span className="ml-1 text-xs text-muted-foreground">({t('categories.das_tag')})</span> : null}
                    {!c.active ? <span className="ml-1 text-xs">({t('common.inactive')})</span> : null}
                  </td>
                  <td className="p-2">{t(`category_direction.${c.direction}`)}</td>
                  <td className="p-2">
                    {c.direction === 'transfer' ? (
                      <span className="text-xs text-muted-foreground">{t('categories.outside_dre')}</span>
                    ) : isAdmin ? (
                      <Select
                        aria-label={`${t('categories.dre_line')}: ${c.name}`}
                        value={c.dre_line ?? ''}
                        disabled={m.update.isPending}
                        onChange={(e) => m.update.mutate({ id: c.id, dre_line: (e.target.value || null) as DreLine | null })}
                      >
                        <option value="">{t('categories.no_line')}</option>
                        {lines.map((l) => <option key={l} value={l}>{t(`dre_line.${l}`)}</option>)}
                      </Select>
                    ) : (
                      <span>{c.dre_line ? t(`dre_line.${c.dre_line}`) : t('categories.no_line')}</span>
                    )}
                  </td>
                  <td className="p-2">
                    {c.direction === 'transfer' ? (
                      '—'
                    ) : isAdmin ? (
                      <Select
                        aria-label={`${t('categories.behavior')}: ${c.name}`}
                        value={c.behavior ?? ''}
                        disabled={m.update.isPending}
                        onChange={(e) => m.update.mutate({ id: c.id, behavior: (e.target.value || null) as CategoryBehavior | null })}
                      >
                        <option value="">{t('categories.behavior_default')}</option>
                        {CATEGORY_BEHAVIORS.map((b) => <option key={b} value={b}>{t(`behavior.${b}`)}</option>)}
                      </Select>
                    ) : (
                      <span>{c.behavior ? t(`behavior.${c.behavior}`) : t('categories.behavior_default')}</span>
                    )}
                  </td>
                  <td className="p-2 text-xs">
                    {c.direction === 'transfer' ? '—' : (c.accounting_code ?? <span className="text-muted-foreground">{t('categories.no_code')}</span>)}
                    {c.activity_kind ? <span className="block text-muted-foreground">{t(`activity.${c.activity_kind}`)}</span> : null}
                  </td>
                  <td className="p-2 text-right whitespace-nowrap">
                    {isAdmin ? (
                      <>
                        <Button size="sm" variant="ghost" onClick={() => open(c)}>{t('common.edit')}</Button>
                        <Button size="sm" variant="ghost" disabled={m.update.isPending} onClick={() => m.update.mutate({ id: c.id, active: !c.active })}>
                          {c.active ? t('common.deactivate') : t('common.activate')}
                        </Button>
                        {!c.is_default ? (
                          <ConfirmButton label={t('common.delete')} pending={m.remove.isPending} onConfirm={async () => { try { await m.remove.mutateAsync(c.id); } catch { /* shown above */ } }} />
                        ) : null}
                      </>
                    ) : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : null}
      {isAdmin && editing !== null ? (
        <form onSubmit={submit} noValidate className="grid gap-3 rounded-md border p-3 sm:grid-cols-3" aria-label={t('categories.form')}>
          <Field label={t('categories.name')} required error={nameError}>
            <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} />
          </Field>
          <Field label={t('categories.direction')}>
            <Select value={formDirection} disabled={editing !== 'new'} onChange={(e) => { setDirection(e.target.value as CategoryDirection); setParent(''); setDreLine(''); }}>
              {CATEGORY_DIRECTIONS.map((d) => <option key={d} value={d}>{t(`category_direction.${d}`)}</option>)}
            </Select>
          </Field>
          <Field label={t('categories.parent')}>
            <Select value={parent} onChange={(e) => setParent(e.target.value)}>
              <option value="">{t('categories.no_parent')}</option>
              {parentOptions.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
          </Field>
          {formDirection !== 'transfer' ? (
            <>
              <Field label={t('categories.dre_line')}>
                <Select value={dreLine} onChange={(e) => setDreLine(e.target.value)}>
                  <option value="">{t('categories.no_line')}</option>
                  {DRE_LINES_BY_DIRECTION[formDirection].map((l) => <option key={l} value={l}>{t(`dre_line.${l}`)}</option>)}
                </Select>
              </Field>
              <Field label={t('categories.behavior')}>
                <Select value={behavior} onChange={(e) => setBehavior(e.target.value)}>
                  <option value="">{t('categories.behavior_default')}</option>
                  {CATEGORY_BEHAVIORS.map((b) => <option key={b} value={b}>{t(`behavior.${b}`)}</option>)}
                </Select>
              </Field>
            </>
          ) : null}
          {formDirection !== 'transfer' ? (
            <Field label={t('categories.accounting_code')}>
              <Input value={accountingCode} onChange={(e) => setAccountingCode(e.target.value)} maxLength={40} />
              <span className="block text-xs text-muted-foreground">{t('categories.accounting_code_help')}</span>
            </Field>
          ) : null}
          {formDirection === 'income' ? (
            <Field label={t('categories.activity_kind')}>
              <Select value={activityKind} onChange={(e) => setActivityKind(e.target.value)}>
                <option value="">{t('categories.activity_inherit')}</option>
                {ACTIVITY_KINDS.map((k) => <option key={k} value={k}>{t(`activity.${k}`)}</option>)}
              </Select>
              <span className="block text-xs text-muted-foreground">{t('categories.activity_help')}</span>
            </Field>
          ) : null}
          {formDirection === 'expense' ? (
            <label className="flex items-center gap-2 self-end text-sm">
              <input type="checkbox" checked={isDas} onChange={(e) => setIsDas(e.target.checked)} />
              {t('categories.is_das')}
              <HelpTip label={t('categories.is_das_help_label')}>{t('categories.is_das_help')}</HelpTip>
            </label>
          ) : null}
          <div className="flex items-end gap-2 sm:col-span-3">
            <Button type="submit" disabled={m.create.isPending || m.update.isPending}>{t('common.save')}</Button>
            <Button type="button" variant="ghost" onClick={() => setEditing(null)}>{t('common.cancel')}</Button>
          </div>
        </form>
      ) : null}
    </section>
  );
}
