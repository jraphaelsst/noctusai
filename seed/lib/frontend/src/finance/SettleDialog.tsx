/**
 * `<SettleDialog/>` — "dar baixa" on an entry (`POST /entries/{id}/settlements`), full or PARTIAL:
 * the amount defaults to what is still open and can be lowered; the entry then stays "parcial".
 */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { Field, FormError, Input, Select } from './controls';
import { FormDialog } from './FormDialog';
import { centsToInput, formatCents, parseMoneyToCents, remainingCents, todayIso } from './format';
import { errorMessage, type FinanceHooks } from './hooks';
import { t } from './i18n';
import type { FinanceEntry, SettlementKind } from './types';

export interface SettleDialogProps {
  hooks: FinanceHooks;
  open: boolean;
  onClose: () => void;
  entry: FinanceEntry;
  onSettled?: () => void;
}

export function SettleDialog({ hooks, open, onClose, entry, onSettled }: SettleDialogProps) {
  const accounts = hooks.useAccounts({ active: true });
  const m = hooks.useEntryMutations();
  const remaining = remainingCents(entry);

  const [kind, setKind] = React.useState<SettlementKind>('payment');
  const [accountId, setAccountId] = React.useState('');
  const [amount, setAmount] = React.useState('');
  const [fee, setFee] = React.useState('');
  const [on, setOn] = React.useState(todayIso());
  const [method, setMethod] = React.useState('');
  const [errors, setErrors] = React.useState<Record<string, string>>({});

  React.useEffect(() => {
    if (!open) return;
    setKind('payment');
    setAccountId(entry.expected_account_id ?? '');
    setAmount(centsToInput(remainingCents(entry)));
    setFee('');
    setOn(todayIso());
    setMethod('');
    setErrors({});
  }, [open, entry]);

  const cents = parseMoneyToCents(amount);
  const isPartial = kind === 'payment' && cents !== null && cents > 0 && cents < remaining;
  const receivable = entry.direction === 'receivable';

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    const next: Record<string, string> = {};
    const feeCents = fee.trim() ? parseMoneyToCents(fee) : 0;
    if (!accountId) next.account = t('settle.account_required');
    if (cents === null || cents <= 0) next.amount = t('entry.amount_invalid');
    else if (kind === 'payment' && cents > remaining) next.amount = t('settle.amount_over', { max: formatCents(remaining) });
    if (feeCents === null) next.fee = t('entry.amount_invalid');
    setErrors(next);
    if (Object.keys(next).length) return;
    try {
      await m.settle.mutateAsync({
        id: entry.id,
        account_id: accountId,
        kind,
        settled_on: on || null,
        amount_cents: cents as number,
        fee_cents: feeCents ?? 0,
        method: method.trim() || null,
      });
      onSettled?.();
      onClose();
    } catch {
      // Surfaced below.
    }
  }

  return (
    <FormDialog
      open={open}
      onClose={onClose}
      title={receivable ? t('settle.title_receivable') : t('settle.title_payable')}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>{t('common.cancel')}</Button>
          <Button type="submit" form="finance-settle-form" disabled={m.settle.isPending}>
            {m.settle.isPending ? t('common.saving') : t('settle.confirm')}
          </Button>
        </>
      }
    >
      <form id="finance-settle-form" onSubmit={submit} noValidate className="grid gap-3 sm:grid-cols-2">
        <p className="text-sm sm:col-span-2">
          <strong>{entry.description}</strong> · {t('settle.open_amount')}: {formatCents(remaining)}
        </p>
        <Field label={t('settle.kind')}>
          <Select value={kind} onChange={(e) => setKind(e.target.value as SettlementKind)}>
            <option value="payment">{receivable ? t('settle.kind_payment_receivable') : t('settle.kind_payment_payable')}</option>
            <option value="refund">{t('settle.kind_refund')}</option>
          </Select>
        </Field>
        <Field label={t('settle.account')} required error={errors.account}>
          <Select value={accountId} onChange={(e) => setAccountId(e.target.value)}>
            <option value="">{t('settle.choose_account')}</option>
            {(accounts.data ?? []).map((a) => (
              <option key={a.id} value={a.id}>{a.name}</option>
            ))}
          </Select>
        </Field>
        <Field label={t('settle.amount')} required error={errors.amount}>
          <Input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
        </Field>
        <Field label={t('settle.date')}>
          <Input type="date" value={on} onChange={(e) => setOn(e.target.value)} />
        </Field>
        <Field label={t('settle.fee')} error={errors.fee}>
          <Input inputMode="decimal" placeholder="0,00" value={fee} onChange={(e) => setFee(e.target.value)} />
        </Field>
        <Field label={t('settle.method')}>
          <Input value={method} onChange={(e) => setMethod(e.target.value)} placeholder={t('settle.method_hint')} maxLength={40} />
        </Field>
        {isPartial ? (
          <p role="status" className="text-xs text-muted-foreground sm:col-span-2">
            {t('settle.partial_notice', { rest: formatCents(remaining - (cents as number)) })}
          </p>
        ) : null}
        <div className="sm:col-span-2">
          <FormError message={m.settle.error ? errorMessage(m.settle.error) : null} />
        </div>
      </form>
    </FormDialog>
  );
}
