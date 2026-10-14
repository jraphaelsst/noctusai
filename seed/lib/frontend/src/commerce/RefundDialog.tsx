/**
 * `<RefundDialog/>` — staff refund of a paid order (CONTRACT P4 §2.4 `POST /orders/{id}/refunds`).
 *
 * Full or partial, with the order's refund history. Every ATTEMPT carries one `Idempotency-Key`: a retry of the
 * SAME input (the connection dropped, a gateway timeout) re-sends the same key and the server returns the same
 * refund; changing the amount or reason starts a new attempt with a new key. A refund the gateway has not
 * confirmed yet comes back `requested` and is shown as "em andamento" — never as done. Admin-only action: the
 * host hides it for staff (UX only, the server enforces).
 */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { Dialog, DialogBody, DialogFooter, DialogHeader } from '../design-system/ui/Dialog';
import { Badge, type BadgeVariant } from '../design-system/ui/Badge';
import { Field, FormError, Input, Textarea } from './controls';
import { useCommerceT } from './i18n';
import { centsToInput, formatCents, formatDateTime, parseMoneyToCents } from './format';
import { errorMessage, type CommerceHooks } from './hooks';
import { newIdempotencyKey, refundableCents, paidCents, doneRefundCents } from './moneyMath';
import type { Order, OrderRefund, RefundStatus } from './types';

export interface RefundDialogProps {
  hooks: CommerceHooks;
  open: boolean;
  onClose: () => void;
  /** The staff order (`GET /orders/{id}`), with `charges` and `refunds`. */
  order: Order;
  locale?: string;
  onDone?: (refund: OrderRefund) => void;
}

const STATUS_VARIANT: Record<RefundStatus, BadgeVariant> = { requested: 'outline', done: 'default', failed: 'destructive' };

export function RefundHistory({ refunds, currency, locale }: { refunds: readonly OrderRefund[]; currency: string; locale?: string }) {
  const { t, locale: loc } = useCommerceT(locale);
  if (refunds.length === 0) return <p className="text-sm text-muted-foreground">{t('refund.history_empty')}</p>;
  return (
    <table className="w-full text-sm" data-testid="refund-history">
      <thead>
        <tr className="border-b text-left text-xs text-muted-foreground">
          <th className="p-2">{t('refund.col_date')}</th>
          <th className="p-2 text-right">{t('refund.col_amount')}</th>
          <th className="p-2">{t('refund.col_reason')}</th>
          <th className="p-2">{t('refund.col_status')}</th>
        </tr>
      </thead>
      <tbody>
        {refunds.map((r) => (
          <tr key={r.id} className="border-b">
            <td className="p-2">{formatDateTime(r.created_at, loc)}</td>
            <td className="p-2 text-right">{formatCents(r.amount_cents, currency, loc)}</td>
            <td className="p-2">{r.reason || '—'}</td>
            <td className="p-2"><Badge variant={STATUS_VARIANT[r.status]} data-status={r.status}>{t(`refund_status.${r.status}`)}</Badge></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function RefundDialog({ hooks, open, onClose, order, locale, onDone }: RefundDialogProps) {
  const { t, locale: loc } = useCommerceT(locale);
  const refund = hooks.useCreateRefund();
  const refundable = refundableCents(order);
  const [mode, setMode] = React.useState<'full' | 'partial'>('full');
  const [amount, setAmount] = React.useState('');
  const [reason, setReason] = React.useState('');
  const [err, setErr] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<OrderRefund | null>(null);
  const key = React.useRef<string>(newIdempotencyKey());

  // A fresh open is a fresh attempt.
  React.useEffect(() => {
    if (!open) return;
    setMode('full');
    setAmount('');
    setReason('');
    setErr(null);
    setResult(null);
    refund.reset();
    key.current = newIdempotencyKey();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `refund.reset` is stable per mount; reset only on open
  }, [open]);

  // Editing the input changes WHAT is asked, so it is a new attempt (new key); retrying unchanged keeps the key.
  const edit = <T,>(set: (v: T) => void) => (v: T) => {
    key.current = newIdempotencyKey();
    setErr(null);
    set(v);
  };

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    const trimmed = reason.trim();
    if (trimmed.length < 3) return setErr(t('refund.reason_required'));
    let cents: number | undefined;
    if (mode === 'partial') {
      const parsed = parseMoneyToCents(amount);
      if (parsed === null || parsed <= 0) return setErr(t('refund.invalid_amount'));
      if (parsed > refundable) return setErr(t('refund.exceeds'));
      cents = parsed;
    }
    setErr(null);
    try {
      const r = await refund.mutateAsync({
        orderId: order.id,
        ...(cents !== undefined ? { amount_cents: cents } : {}),
        reason: trimmed,
        idempotencyKey: key.current,
      });
      setResult(r);
      onDone?.(r);
    } catch (e) {
      setErr(errorMessage(e)); // the key is kept: pressing "Reembolsar" again is the SAME attempt
    }
  }

  const fmt = (c: number) => formatCents(c, order.currency, loc);
  const pending = refund.isPending;

  return (
    <Dialog open={open} onClose={onClose} title={t('refund.title')}>
      <form onSubmit={submit} noValidate>
        <DialogHeader>
          <h3 className="text-sm font-semibold">{t('refund.title')}</h3>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <p className="text-sm" data-testid="refund-balance">
            {t('refund.balance', { amount: fmt(refundable), paid: fmt(paidCents(order)), refunded: fmt(doneRefundCents(order.refunds)) })}
          </p>

          {result ? (
            result.status === 'requested' ? (
              <p role="status" className="rounded-md border p-3 text-sm" data-testid="refund-in-progress">
                {t('refund.in_progress', { amount: fmt(result.amount_cents) })}
              </p>
            ) : (
              <p role="status" className="rounded-md border border-green-500/40 bg-green-500/10 p-3 text-sm">
                {t('refund.done', { amount: fmt(result.amount_cents) })}
              </p>
            )
          ) : (
            <>
              <fieldset className="space-y-1">
                <label className="flex items-center gap-2 text-sm">
                  <input type="radio" name="refund_mode" checked={mode === 'full'} onChange={() => edit(setMode)('full')} />
                  {t('refund.full')} ({fmt(refundable)})
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input type="radio" name="refund_mode" checked={mode === 'partial'} onChange={() => edit(setMode)('partial')} />
                  {t('refund.partial')}
                </label>
              </fieldset>
              {mode === 'partial' ? (
                <Field label={t('refund.amount')} required>
                  <Input inputMode="decimal" value={amount} onChange={(e) => edit(setAmount)(e.target.value)} placeholder={centsToInput(refundable)} />
                  <span className="text-xs text-muted-foreground">{t('refund.amount_hint', { max: fmt(refundable) })}</span>
                </Field>
              ) : null}
              <Field label={t('refund.reason')} required>
                <Textarea rows={2} value={reason} onChange={(e) => edit(setReason)(e.target.value)} />
                <span className="text-xs text-muted-foreground">{t('refund.reason_hint')}</span>
              </Field>
              <FormError message={err} />
              {err ? <p className="text-xs text-muted-foreground">{t('refund.retry_hint')}</p> : null}
            </>
          )}

          <section aria-label={t('refund.history')} className="space-y-1">
            <h4 className="text-xs font-semibold">{t('refund.history')}</h4>
            <RefundHistory refunds={order.refunds ?? []} currency={order.currency} locale={locale} />
          </section>
        </DialogBody>
        <DialogFooter className="gap-2">
          <Button type="button" onClick={onClose} disabled={pending}>{t('common.back')}</Button>
          {result ? null : (
            <Button type="submit" variant="primary" disabled={pending || refundable <= 0}>
              {pending ? t('refund.submitting') : t('refund.submit')}
            </Button>
          )}
        </DialogFooter>
      </form>
    </Dialog>
  );
}
