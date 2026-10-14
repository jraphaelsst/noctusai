/**
 * `<EntryDetailDialog/>` — one entry: facts, its settlements (reverse a baixa with a reason),
 * cancel, attachments. Id-keyed detail: no placeholderData (never shows another entry's history).
 */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { ConfirmButton, EntryStatusChip, FormError, ListSkeleton, RetryError, Textarea, Field } from './controls';
import { AttachmentsPanel } from './AttachmentsPanel';
import { FormDialog } from './FormDialog';
import { formatCents, formatDate, remainingCents } from './format';
import { errorMessage, type FinanceHooks } from './hooks';
import { t } from './i18n';
import type { FinanceEntry, Settlement } from './types';

export interface EntryDetailDialogProps {
  hooks: FinanceHooks;
  entryId: string | null;
  onClose: () => void;
  isAdmin?: boolean;
  onEdit?: (entry: FinanceEntry) => void;
  onSettle?: (entry: FinanceEntry) => void;
}

export function EntryDetailDialog({ hooks, entryId, onClose, isAdmin = false, onEdit, onSettle }: EntryDetailDialogProps) {
  const detail = hooks.useEntry(entryId);
  const accounts = hooks.useAccounts();
  const m = hooks.useEntryMutations();
  const [reversing, setReversing] = React.useState<Settlement | null>(null);
  const [reason, setReason] = React.useState('');
  const [reasonError, setReasonError] = React.useState<string | null>(null);

  const accountName = (id: string) => accounts.data?.find((a) => a.id === id)?.name ?? '—';
  const entry = detail.data;
  const open = entry ? entry.status === 'open' || entry.status === 'partial' : false;

  async function submitReverse(ev: React.FormEvent) {
    ev.preventDefault();
    if (!reversing) return;
    if (reason.trim().length < 3) {
      setReasonError(t('reverse.reason_short'));
      return;
    }
    setReasonError(null);
    try {
      await m.reverse.mutateAsync({ settlementId: reversing.id, reason: reason.trim() });
      setReversing(null);
      setReason('');
    } catch {
      // Surfaced below.
    }
  }

  const mutErr = m.cancel.error ?? m.reverse.error;
  let body: React.ReactNode;
  if (detail.showSkeleton) body = <ListSkeleton rows={4} />;
  else if (detail.isError && !entry) {
    body = <RetryError message={`${t('common.error_loading')}: ${errorMessage(detail.error)}`} onRetry={() => detail.refetch()} retryLabel={t('common.retry')} />;
  } else if (entry) {
    body = (
      <div className="space-y-4" aria-busy={detail.isRefreshing}>
        <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-2">
          <div><dt className="text-xs text-muted-foreground">{t('entry.description')}</dt><dd>{entry.description}</dd></div>
          <div><dt className="text-xs text-muted-foreground">{t('entry.status')}</dt><dd><EntryStatusChip status={entry.status} overdue={entry.overdue} /></dd></div>
          <div><dt className="text-xs text-muted-foreground">{t('entry.counterparty')}</dt><dd>{entry.counterparty_name ?? '—'}</dd></div>
          <div><dt className="text-xs text-muted-foreground">{t('entry.due_date')}</dt><dd>{formatDate(entry.due_date)}</dd></div>
          <div><dt className="text-xs text-muted-foreground">{t('entry.amount')}</dt><dd>{formatCents(entry.amount_cents)}</dd></div>
          <div><dt className="text-xs text-muted-foreground">{t('entry.settled')}</dt><dd>{formatCents(entry.settled_cents)} · {t('entry.remaining')}: {formatCents(remainingCents(entry))}</dd></div>
          {entry.installment_n && entry.installment_total ? (
            <div><dt className="text-xs text-muted-foreground">{t('entry.installment')}</dt><dd>{entry.installment_n}/{entry.installment_total}</dd></div>
          ) : null}
          {entry.notes ? <div className="sm:col-span-2"><dt className="text-xs text-muted-foreground">{t('entry.notes')}</dt><dd>{entry.notes}</dd></div> : null}
        </dl>

        <section className="space-y-2" aria-label={t('entry.settlements')}>
          <h4 className="text-sm font-semibold">{t('entry.settlements')}</h4>
          {entry.settlements.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t('entry.no_settlements')}</p>
          ) : (
            <ul className="divide-y rounded-md border text-sm">
              {entry.settlements.map((s) => (
                <li key={s.id} className="flex flex-wrap items-center justify-between gap-2 p-2">
                  <span className={s.reversed_at ? 'text-muted-foreground line-through' : ''}>
                    {formatDate(s.settled_on)} · {s.kind === 'refund' ? t('settle.kind_refund') : t('settle.kind_payment')} {formatCents(s.amount_cents)}
                    {s.fee_cents > 0 ? ` (${t('settle.fee')}: ${formatCents(s.fee_cents)})` : ''} · {accountName(s.account_id)}
                  </span>
                  {s.reversed_at ? (
                    <span className="text-xs text-muted-foreground">{t('reverse.done')}: {s.reversal_reason}</span>
                  ) : isAdmin ? (
                    <Button size="sm" variant="ghost" onClick={() => { setReversing(s); setReason(''); setReasonError(null); }}>
                      {t('reverse.action')}
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
          {reversing ? (
            <form onSubmit={submitReverse} noValidate className="space-y-2 rounded-md border p-3">
              <p className="text-sm">{t('reverse.help', { amount: formatCents(reversing.amount_cents) })}</p>
              <Field label={t('reverse.reason')} required error={reasonError}>
                <Textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} />
              </Field>
              <div className="flex gap-2">
                <Button type="submit" variant="destructive" size="sm" disabled={m.reverse.isPending}>{t('reverse.confirm')}</Button>
                <Button type="button" variant="ghost" size="sm" onClick={() => setReversing(null)}>{t('common.cancel')}</Button>
              </div>
            </form>
          ) : null}
        </section>

        <AttachmentsPanel hooks={hooks} entryId={entry.id} isAdmin={isAdmin} />
        <FormError message={mutErr ? errorMessage(mutErr) : null} />
      </div>
    );
  }

  return (
    <FormDialog
      open={!!entryId}
      onClose={onClose}
      title={t('entry.detail_title')}
      wide
      footer={
        entry && isAdmin ? (
          <>
            {open && entry.settled_cents === 0 ? (
              <ConfirmButton
                label={t('entry.cancel')}
                confirmLabel={t('entry.cancel_confirm')}
                pending={m.cancel.isPending}
                onConfirm={async () => {
                  try {
                    await m.cancel.mutateAsync(entry.id);
                  } catch {
                    // Surfaced through `m.cancel.error`.
                  }
                }}
              />
            ) : null}
            {entry.status !== 'cancelled' ? <Button variant="outline" size="sm" onClick={() => onEdit?.(entry)}>{t('common.edit')}</Button> : null}
            {open ? <Button size="sm" onClick={() => onSettle?.(entry)}>{t('entry.settle')}</Button> : null}
          </>
        ) : undefined
      }
    >
      {body}
    </FormDialog>
  );
}
