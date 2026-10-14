/** `<TransferDialog/>` — move money between two of the org's accounts (`POST /transfers`). Not an entry. */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { Field, FormError, Input, Select } from './controls';
import { FormDialog } from './FormDialog';
import { parseMoneyToCents, todayIso } from './format';
import { errorMessage, type FinanceHooks } from './hooks';
import { t } from './i18n';

export interface TransferDialogProps {
  hooks: FinanceHooks;
  open: boolean;
  onClose: () => void;
  defaultFromId?: string;
}

export function TransferDialog({ hooks, open, onClose, defaultFromId }: TransferDialogProps) {
  const accounts = hooks.useAccounts({ active: true });
  const transfer = hooks.useTransfer();
  const [from, setFrom] = React.useState('');
  const [to, setTo] = React.useState('');
  const [amount, setAmount] = React.useState('');
  const [on, setOn] = React.useState(todayIso());
  const [description, setDescription] = React.useState('');
  const [errors, setErrors] = React.useState<Record<string, string>>({});

  React.useEffect(() => {
    if (!open) return;
    setFrom(defaultFromId ?? '');
    setTo('');
    setAmount('');
    setOn(todayIso());
    setDescription('');
    setErrors({});
  }, [open, defaultFromId]);

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    const next: Record<string, string> = {};
    const cents = parseMoneyToCents(amount);
    if (!from) next.from = t('common.required');
    if (!to) next.to = t('common.required');
    else if (to === from) next.to = t('transfer.same_account');
    if (cents === null || cents <= 0) next.amount = t('entry.amount_invalid');
    setErrors(next);
    if (Object.keys(next).length) return;
    try {
      await transfer.mutateAsync({
        from_account_id: from,
        to_account_id: to,
        amount_cents: cents as number,
        occurred_on: on || null,
        description: description.trim() || null,
      });
      onClose();
    } catch {
      // Surfaced below.
    }
  }

  const options = accounts.data ?? [];
  return (
    <FormDialog
      open={open}
      onClose={onClose}
      title={t('transfer.title')}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>{t('common.cancel')}</Button>
          <Button type="submit" form="finance-transfer-form" disabled={transfer.isPending}>
            {transfer.isPending ? t('common.saving') : t('transfer.confirm')}
          </Button>
        </>
      }
    >
      <form id="finance-transfer-form" onSubmit={submit} noValidate className="grid gap-3 sm:grid-cols-2">
        <p className="text-xs text-muted-foreground sm:col-span-2">{t('transfer.help')}</p>
        <Field label={t('transfer.from')} required error={errors.from}>
          <Select value={from} onChange={(e) => setFrom(e.target.value)}>
            <option value="">{t('settle.choose_account')}</option>
            {options.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </Select>
        </Field>
        <Field label={t('transfer.to')} required error={errors.to}>
          <Select value={to} onChange={(e) => setTo(e.target.value)}>
            <option value="">{t('settle.choose_account')}</option>
            {options.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </Select>
        </Field>
        <Field label={t('transfer.amount')} required error={errors.amount}>
          <Input inputMode="decimal" placeholder="0,00" value={amount} onChange={(e) => setAmount(e.target.value)} />
        </Field>
        <Field label={t('transfer.date')}>
          <Input type="date" value={on} onChange={(e) => setOn(e.target.value)} />
        </Field>
        <div className="sm:col-span-2">
          <Field label={t('transfer.description')}>
            <Input value={description} onChange={(e) => setDescription(e.target.value)} maxLength={300} />
          </Field>
        </div>
        <div className="sm:col-span-2">
          <FormError message={transfer.error ? errorMessage(transfer.error) : null} />
        </div>
      </form>
    </FormDialog>
  );
}
