/** `<RecurrencesManager/>` — lançamentos recorrentes (aluguel, assinaturas...). A template + a frequency + the next date. */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { EmptyState, Field, FormError, Input, ListSkeleton, PageHeader, RefreshingBar, RetryError, Select } from './controls';
import { centsToInput, formatCents, formatDate, parseMoneyToCents, todayIso } from './format';
import { errorMessage, type FinanceHooks } from './hooks';
import { t } from './i18n';
import { ENTRY_DIRECTIONS, FREQUENCIES, type EntryDirection, type Frequency, type Recurrence } from './types';

export interface RecurrencesManagerProps {
  hooks: FinanceHooks;
  isAdmin?: boolean;
}

export function RecurrencesManager({ hooks, isAdmin = false }: RecurrencesManagerProps) {
  const list = hooks.useRecurrences();
  const categories = hooks.useCategories();
  const accounts = hooks.useAccounts({ active: true });
  const m = hooks.useRecurrenceMutations();

  const [editing, setEditing] = React.useState<Recurrence | 'new' | null>(null);
  const [direction, setDirection] = React.useState<EntryDirection>('payable');
  const [description, setDescription] = React.useState('');
  const [counterparty, setCounterparty] = React.useState('');
  const [amount, setAmount] = React.useState('');
  const [categoryId, setCategoryId] = React.useState('');
  const [accountId, setAccountId] = React.useState('');
  const [frequency, setFrequency] = React.useState<Frequency>('monthly');
  const [nextDate, setNextDate] = React.useState(todayIso());
  const [endDate, setEndDate] = React.useState('');
  const [errors, setErrors] = React.useState<Record<string, string>>({});

  function open(r: Recurrence | null) {
    setEditing(r ?? 'new');
    setDirection(r?.template.direction ?? 'payable');
    setDescription(r?.template.description ?? '');
    setCounterparty(r?.template.counterparty_name ?? '');
    setAmount(r ? centsToInput(r.template.amount_cents) : '');
    setCategoryId(r?.template.category_id ?? '');
    setAccountId(r?.template.expected_account_id ?? '');
    setFrequency(r?.frequency ?? 'monthly');
    setNextDate(r?.next_date ?? todayIso());
    setEndDate(r?.end_date ?? '');
    setErrors({});
  }

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    const next: Record<string, string> = {};
    const cents = parseMoneyToCents(amount);
    if (!description.trim()) next.description = t('common.required');
    if (cents === null || cents <= 0) next.amount = t('entry.amount_invalid');
    if (!nextDate) next.next_date = t('common.required');
    if (endDate && nextDate && endDate < nextDate) next.end_date = t('recurrences.end_before_next');
    setErrors(next);
    if (Object.keys(next).length) return;
    const template = {
      direction,
      description: description.trim(),
      counterparty_name: counterparty.trim() || null,
      category_id: categoryId || null,
      expected_account_id: accountId || null,
      amount_cents: cents as number,
    };
    try {
      if (editing === 'new') await m.create.mutateAsync({ template, frequency, next_date: nextDate, end_date: endDate || null });
      else if (editing) await m.update.mutateAsync({ id: editing.id, template, frequency, next_date: nextDate, end_date: endDate || null });
      setEditing(null);
    } catch {
      // Surfaced below.
    }
  }

  if (list.showSkeleton) return <ListSkeleton />;
  if (list.isError && !list.data) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(list.error)}`} onRetry={() => list.refetch()} retryLabel={t('common.retry')} />;
  }
  const rows = list.data ?? [];
  const mutErr = m.create.error ?? m.update.error;
  const wanted = direction === 'receivable' ? 'income' : 'expense';

  return (
    <section className="space-y-3" aria-busy={list.isRefreshing}>
      <PageHeader
        title={t('recurrences.title')}
        subtitle={t('recurrences.subtitle')}
        actions={isAdmin ? <Button size="sm" onClick={() => open(null)}>{t('recurrences.add')}</Button> : undefined}
      />
      <RefreshingBar active={list.isRefreshing} label={t('common.refreshing')} />
      <FormError message={mutErr ? errorMessage(mutErr) : null} />
      {rows.length === 0 && editing === null ? <EmptyState message={t('recurrences.empty')} /> : null}
      <ul className="divide-y rounded-md border">
        {rows.map((r) => (
          <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 p-3 text-sm">
            <span className={r.active ? '' : 'text-muted-foreground'}>
              <strong>{r.template.description}</strong>{' '}
              <span className="text-xs text-muted-foreground">
                {t(`entry.direction_${r.template.direction}`)} · {formatCents(r.template.amount_cents)} · {t(`frequency.${r.frequency}`)} · {t('recurrences.next')} {formatDate(r.next_date)}
                {r.end_date ? ` · ${t('recurrences.until')} ${formatDate(r.end_date)}` : ''}
                {!r.active ? ` · ${t('common.inactive')}` : ''}
              </span>
            </span>
            {isAdmin ? (
              <span className="flex items-center gap-1">
                <Button size="sm" variant="ghost" onClick={() => open(r)}>{t('common.edit')}</Button>
                <Button size="sm" variant="ghost" disabled={m.update.isPending} onClick={() => m.update.mutate({ id: r.id, active: !r.active })}>
                  {r.active ? t('recurrences.pause') : t('recurrences.resume')}
                </Button>
              </span>
            ) : null}
          </li>
        ))}
      </ul>
      {isAdmin && editing !== null ? (
        <form onSubmit={submit} noValidate className="grid gap-3 rounded-md border p-3 sm:grid-cols-3" aria-label={t('recurrences.form')}>
          <Field label={t('recurrences.direction')}>
            <Select value={direction} onChange={(e) => { setDirection(e.target.value as EntryDirection); setCategoryId(''); }}>
              {ENTRY_DIRECTIONS.map((d) => <option key={d} value={d}>{t(`entry.direction_${d}`)}</option>)}
            </Select>
          </Field>
          <div className="sm:col-span-2">
            <Field label={t('entry.description')} required error={errors.description}>
              <Input value={description} onChange={(e) => setDescription(e.target.value)} maxLength={300} />
            </Field>
          </div>
          <Field label={t('entry.counterparty')}>
            <Input value={counterparty} onChange={(e) => setCounterparty(e.target.value)} maxLength={200} />
          </Field>
          <Field label={t('entry.amount')} required error={errors.amount}>
            <Input inputMode="decimal" placeholder="0,00" value={amount} onChange={(e) => setAmount(e.target.value)} />
          </Field>
          <Field label={t('entry.category')}>
            <Select value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
              <option value="">{t('entry.no_category')}</option>
              {(categories.data ?? []).filter((c) => c.direction === wanted && c.active).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
          </Field>
          <Field label={t('entry.expected_account')}>
            <Select value={accountId} onChange={(e) => setAccountId(e.target.value)}>
              <option value="">{t('entry.no_account')}</option>
              {(accounts.data ?? []).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </Select>
          </Field>
          <Field label={t('recurrences.frequency')}>
            <Select value={frequency} onChange={(e) => setFrequency(e.target.value as Frequency)}>
              {FREQUENCIES.map((f) => <option key={f} value={f}>{t(`frequency.${f}`)}</option>)}
            </Select>
          </Field>
          <Field label={t('recurrences.next_date')} required error={errors.next_date}>
            <Input type="date" value={nextDate} onChange={(e) => setNextDate(e.target.value)} />
          </Field>
          <Field label={t('recurrences.end_date')} error={errors.end_date}>
            <Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
          </Field>
          <div className="flex items-end gap-2 sm:col-span-3">
            <Button type="submit" disabled={m.create.isPending || m.update.isPending}>{t('common.save')}</Button>
            <Button type="button" variant="ghost" onClick={() => setEditing(null)}>{t('common.cancel')}</Button>
          </div>
        </form>
      ) : null}
    </section>
  );
}
