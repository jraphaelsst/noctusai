/** `<EntryDialog/>` — create or edit a payable / receivable (`POST /entries`, `PATCH /entries/{id}`). */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { Field, FormError, Input, Select, Textarea } from './controls';
import { FormDialog } from './FormDialog';
import { centsToInput, parseMoneyToCents, toCompetenceMonth, todayIso } from './format';
import { errorMessage, type FinanceHooks } from './hooks';
import { t } from './i18n';
import type { EntryDirection, FinanceEntry } from './types';

export const MAX_INSTALLMENTS = 120;

export interface EntryDialogProps {
  hooks: FinanceHooks;
  open: boolean;
  onClose: () => void;
  /** Direction of a NEW entry (an edited entry keeps its own). */
  direction: EntryDirection;
  /** Present ⇒ edit mode. */
  entry?: FinanceEntry | null;
  onSaved?: (rows: FinanceEntry[]) => void;
}

export function EntryDialog({ hooks, open, onClose, direction, entry, onSaved }: EntryDialogProps) {
  const editing = !!entry;
  const dir = entry?.direction ?? direction;
  const categories = hooks.useCategories();
  const costCenters = hooks.useCostCenters();
  const accounts = hooks.useAccounts({ active: true });
  const m = hooks.useEntryMutations();

  const [description, setDescription] = React.useState('');
  const [counterparty, setCounterparty] = React.useState('');
  const [amount, setAmount] = React.useState('');
  const [due, setDue] = React.useState(todayIso());
  const [competence, setCompetence] = React.useState('');
  const [categoryId, setCategoryId] = React.useState('');
  const [costCenterId, setCostCenterId] = React.useState('');
  const [accountId, setAccountId] = React.useState('');
  const [installments, setInstallments] = React.useState('1');
  const [notes, setNotes] = React.useState('');
  const [errors, setErrors] = React.useState<Record<string, string>>({});

  React.useEffect(() => {
    if (!open) return;
    setDescription(entry?.description ?? '');
    setCounterparty(entry?.counterparty_name ?? '');
    setAmount(entry ? centsToInput(entry.amount_cents) : '');
    setDue(entry?.due_date ?? todayIso());
    setCompetence(entry?.competence_month?.slice(0, 7) ?? '');
    setCategoryId(entry?.category_id ?? '');
    setCostCenterId(entry?.cost_center_id ?? '');
    setAccountId(entry?.expected_account_id ?? '');
    setInstallments('1');
    setNotes(entry?.notes ?? '');
    setErrors({});
  }, [open, entry]);

  const wantedCategoryDirection = dir === 'receivable' ? 'income' : 'expense';
  const categoryOptions = (categories.data ?? []).filter((c) => c.direction === wantedCategoryDirection && c.active);
  const mutErr = m.create.error ?? m.update.error;

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    const next: Record<string, string> = {};
    const cents = parseMoneyToCents(amount);
    if (!description.trim()) next.description = t('common.required');
    if (cents === null || cents <= 0) next.amount = t('entry.amount_invalid');
    if (!/^\d{4}-\d{2}-\d{2}$/.test(due)) next.due = t('common.required');
    const n = Number(installments);
    if (!editing && (!Number.isInteger(n) || n < 1 || n > MAX_INSTALLMENTS)) next.installments = t('entry.installments_invalid', { max: MAX_INSTALLMENTS });
    setErrors(next);
    if (Object.keys(next).length) return;

    const common = {
      description: description.trim(),
      counterparty_name: counterparty.trim() || null,
      category_id: categoryId || null,
      cost_center_id: costCenterId || null,
      expected_account_id: accountId || null,
      due_date: due,
      competence_month: competence ? `${competence}-01` : toCompetenceMonth(due),
      amount_cents: cents as number,
      notes: notes.trim() || null,
    };
    try {
      if (editing && entry) {
        const saved = await m.update.mutateAsync({ id: entry.id, ...common });
        onSaved?.([saved]);
      } else {
        const saved = await m.create.mutateAsync({ direction: dir, installments: n, ...common });
        onSaved?.(saved);
      }
      onClose();
    } catch {
      // Surfaced below through the mutation error.
    }
  }

  const busy = m.create.isPending || m.update.isPending;
  return (
    <FormDialog
      open={open}
      onClose={onClose}
      title={editing ? t('entry.edit_title') : dir === 'receivable' ? t('entry.new_receivable') : t('entry.new_payable')}
      wide
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>{t('common.cancel')}</Button>
          <Button type="submit" form="finance-entry-form" disabled={busy}>
            {busy ? t('common.saving') : t('common.save')}
          </Button>
        </>
      }
    >
      <form id="finance-entry-form" onSubmit={submit} noValidate className="grid gap-3 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <Field label={t('entry.description')} required error={errors.description}>
            <Input value={description} onChange={(e) => setDescription(e.target.value)} maxLength={300} />
          </Field>
        </div>
        <Field label={dir === 'receivable' ? t('entry.counterparty_receivable') : t('entry.counterparty_payable')}>
          <Input value={counterparty} onChange={(e) => setCounterparty(e.target.value)} maxLength={200} />
        </Field>
        <Field label={t('entry.amount')} required error={errors.amount}>
          <Input inputMode="decimal" placeholder="0,00" value={amount} onChange={(e) => setAmount(e.target.value)} />
        </Field>
        <Field label={t('entry.due_date')} required error={errors.due}>
          <Input type="date" value={due} onChange={(e) => setDue(e.target.value)} />
        </Field>
        <Field label={t('entry.competence')}>
          <Input type="month" value={competence} onChange={(e) => setCompetence(e.target.value)} />
        </Field>
        <Field label={t('entry.category')}>
          <Select value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
            <option value="">{t('entry.no_category')}</option>
            {categoryOptions.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </Select>
        </Field>
        <Field label={t('entry.cost_center')}>
          <Select value={costCenterId} onChange={(e) => setCostCenterId(e.target.value)}>
            <option value="">{t('entry.no_cost_center')}</option>
            {(costCenters.data ?? []).filter((c) => c.active).map((c) => (
              <option key={c.id} value={c.id}>{c.code} · {c.name}</option>
            ))}
          </Select>
        </Field>
        <Field label={t('entry.expected_account')}>
          <Select value={accountId} onChange={(e) => setAccountId(e.target.value)}>
            <option value="">{t('entry.no_account')}</option>
            {(accounts.data ?? []).map((a) => (
              <option key={a.id} value={a.id}>{a.name}</option>
            ))}
          </Select>
        </Field>
        {!editing ? (
          <Field label={t('entry.installments')} error={errors.installments}>
            <Input type="number" min={1} max={MAX_INSTALLMENTS} value={installments} onChange={(e) => setInstallments(e.target.value)} />
          </Field>
        ) : null}
        <div className="sm:col-span-2">
          <Field label={t('entry.notes')}>
            <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} maxLength={2000} />
          </Field>
        </div>
        {!editing ? <p className="text-xs text-muted-foreground sm:col-span-2">{t('entry.installments_help')}</p> : null}
        <div className="sm:col-span-2">
          <FormError message={mutErr ? errorMessage(mutErr) : null} />
        </div>
      </form>
    </FormDialog>
  );
}
