/**
 * `<OrderMoneyPanel/>` — the money side of one staff order (CONTRACT P4 §5): charge attempts (method, parcelas,
 * what was charged with interest), refunds with the "em andamento" state, payment reminders sent and the
 * order's invoices. Admin-only actions (refund, issue / cancel invoice) are hidden for staff — UX only, the
 * server enforces. Reads the order handed in (the `GET /orders/{id}` money view) and the invoices query.
 */
import * as React from 'react';
import { Badge, type BadgeVariant } from '../design-system/ui/Badge';
import { Button } from '../design-system/ui/Button';
import { EmptyState, FormError, Input, ListSkeleton, RefreshingBar, RetryError, Select } from './controls';
import { useCommerceT } from './i18n';
import { formatCents, formatDateTime } from './format';
import { errorMessage, type CommerceHooks } from './hooks';
import { hasRefundInProgress, doneRefundCents, refundableCents } from './moneyMath';
import { RefundDialog, RefundHistory } from './RefundDialog';
import { INVOICE_KINDS, type Invoice, type InvoiceKind, type InvoiceStatus } from './fiscalTypes';
import type { ChargeAttemptStatus, Order } from './types';

export interface OrderMoneyPanelProps {
  hooks: CommerceHooks;
  order: Order;
  /** Org admin (UX only). Default `false`: staff see the money, not the actions. */
  isAdmin?: boolean;
  locale?: string;
}

const REFUNDABLE_STATUSES: ReadonlySet<Order['status']> = new Set(['paid', 'partially_refunded']);
const CHARGE_VARIANT: Record<ChargeAttemptStatus, BadgeVariant> = {
  pending: 'outline', paid: 'default', expired: 'muted', cancelled: 'muted', failed: 'destructive',
};
const INVOICE_VARIANT: Record<InvoiceStatus, BadgeVariant> = {
  processing: 'outline', authorized: 'default', rejected: 'destructive', cancelled: 'muted', error: 'destructive',
};

function InvoicesSection({ hooks, orderId, isAdmin, locale }: { hooks: CommerceHooks; orderId: string; isAdmin: boolean; locale?: string }) {
  const { t, locale: loc } = useCommerceT(locale);
  const invoices = hooks.useOrderInvoices(orderId);
  const { issue, cancel } = hooks.useInvoiceMutations(orderId);
  const [kind, setKind] = React.useState<InvoiceKind>('nfse');
  const [cancelling, setCancelling] = React.useState<string | null>(null);
  const [reason, setReason] = React.useState('');

  return (
    <section aria-label={t('money.invoices')} className="space-y-2" aria-busy={invoices.isRefreshing}>
      <h3 className="text-sm font-semibold">{t('money.invoices')}</h3>
      <RefreshingBar active={invoices.isRefreshing} label={t('common.refreshing')} />
      {invoices.showSkeleton ? (
        <ListSkeleton rows={2} />
      ) : invoices.isError && !invoices.data ? (
        <RetryError message={`${t('common.error_loading')}: ${errorMessage(invoices.error)}`} onRetry={() => invoices.refetch()} retryLabel={t('common.retry')} />
      ) : (invoices.data ?? []).length === 0 ? (
        <EmptyState message={t('money.invoices_empty')} />
      ) : (
        <ul className="divide-y rounded-md border text-sm" data-testid="invoice-list">
          {(invoices.data ?? []).map((inv: Invoice) => (
            <li key={inv.id} className="space-y-1 p-2">
              <div className="flex flex-wrap items-center gap-2">
                <strong>{t(`invoice_kind.${inv.kind}`)}</strong>
                {inv.number ? <span>{t('money.invoice_number', { number: inv.number })}</span> : null}
                <Badge variant={INVOICE_VARIANT[inv.status]} data-status={inv.status}>{t(`invoice_status.${inv.status}`)}</Badge>
                <span className="text-xs text-muted-foreground">{formatDateTime(inv.issued_at ?? inv.created_at, loc)}</span>
                {isAdmin && inv.status === 'authorized' && cancelling !== inv.id ? (
                  <Button variant="ghost" onClick={() => { setCancelling(inv.id); setReason(''); }}>{t('money.invoice_cancel')}</Button>
                ) : null}
              </div>
              {inv.rejection?.reasons?.length ? <p className="text-xs text-destructive">{inv.rejection.reasons.join(' · ')}</p> : null}
              {cancelling === inv.id ? (
                <div className="flex flex-wrap items-center gap-2">
                  <Input aria-label={t('money.invoice_cancel_reason')} placeholder={t('money.invoice_cancel_reason')} value={reason} onChange={(e) => setReason(e.target.value)} />
                  <Button
                    variant="destructive"
                    disabled={cancel.isPending || reason.trim().length < 3}
                    onClick={async () => {
                      try {
                        await cancel.mutateAsync({ id: inv.id, reason: reason.trim() });
                        setCancelling(null);
                      } catch {
                        // surfaced via `cancel.error` below
                      }
                    }}
                  >
                    {t('money.invoice_cancel_confirm')}
                  </Button>
                  <Button variant="ghost" onClick={() => setCancelling(null)}>{t('common.back')}</Button>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {isAdmin ? (
        <div className="flex items-center gap-2">
          <Select aria-label={t('money.invoices')} value={kind} onChange={(e) => setKind(e.target.value as InvoiceKind)}>
            {INVOICE_KINDS.map((k) => <option key={k} value={k}>{t(`invoice_kind.${k}`)}</option>)}
          </Select>
          <Button variant="outline" disabled={issue.isPending} onClick={() => issue.mutate(kind)}>
            {issue.isPending ? t('money.invoice_issuing') : t('money.invoice_issue')}
          </Button>
        </div>
      ) : null}
      <FormError message={issue.error ? errorMessage(issue.error) : cancel.error ? errorMessage(cancel.error) : null} />
    </section>
  );
}

export function OrderMoneyPanel({ hooks, order, isAdmin = false, locale }: OrderMoneyPanelProps) {
  const { t, locale: loc } = useCommerceT(locale);
  const [refunding, setRefunding] = React.useState(false);
  const fmt = (c: number) => formatCents(c, order.currency, loc);
  const charges = order.charges ?? [];
  const refunds = order.refunds ?? [];
  const reminders = order.reminders ?? [];
  const canRefund = isAdmin && REFUNDABLE_STATUSES.has(order.status) && refundableCents(order) > 0;

  return (
    <section className="space-y-5 rounded-md border p-4" aria-label={t('money.title')} data-testid="order-money">
      <h2 className="text-base font-semibold">{t('money.title')}</h2>

      <section aria-label={t('money.charges')} className="space-y-2">
        <h3 className="text-sm font-semibold">{t('money.charges')}</h3>
        {charges.length === 0 ? (
          <EmptyState message={t('money.charges_empty')} />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th className="p-2">{t('money.col_attempt')}</th>
                <th className="p-2">{t('money.col_method')}</th>
                <th className="p-2">{t('money.col_installments')}</th>
                <th className="p-2 text-right">{t('money.col_amount')}</th>
                <th className="p-2">{t('money.col_status')}</th>
              </tr>
            </thead>
            <tbody>
              {charges.map((c) => (
                <tr key={c.id} className="border-b">
                  <td className="p-2">#{c.attempt}</td>
                  <td className="p-2">{t(`payment.${c.payment_method}`)}</td>
                  <td className="p-2">{t('money.installments_value', { count: c.installment_count })}</td>
                  <td className="p-2 text-right">{fmt(c.amount_cents)}</td>
                  <td className="p-2"><Badge variant={CHARGE_VARIANT[c.status]} data-status={c.status}>{t(`charge_status.${c.status}`)}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section aria-label={t('refund.history')} className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">{t('refund.history')}</h3>
          <div className="flex items-center gap-3">
            {doneRefundCents(refunds) > 0 ? <span className="text-sm">{t('money.refunded_total', { amount: fmt(doneRefundCents(refunds)) })}</span> : null}
            {canRefund ? <Button variant="outline" onClick={() => setRefunding(true)}>{t('money.refund_action')}</Button> : null}
          </div>
        </div>
        {hasRefundInProgress(refunds) ? (
          <p role="status" className="text-xs text-muted-foreground" data-testid="money-refund-in-progress">
            {t('refund_status.requested')}
          </p>
        ) : null}
        <RefundHistory refunds={refunds} currency={order.currency} locale={locale} />
      </section>

      <section aria-label={t('money.reminders')} className="space-y-1">
        <h3 className="text-sm font-semibold">{t('money.reminders')}</h3>
        {reminders.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('money.reminders_empty')}</p>
        ) : (
          <ul className="text-sm">
            {reminders.map((r) => (
              <li key={r.kind}>{t('money.reminder_sent', { kind: t(`reminder.${r.kind}`), at: formatDateTime(r.sent_at, loc) })}</li>
            ))}
          </ul>
        )}
      </section>

      <InvoicesSection hooks={hooks} orderId={order.id} isAdmin={isAdmin} locale={locale} />

      {canRefund ? <RefundDialog hooks={hooks} open={refunding} onClose={() => setRefunding(false)} order={order} locale={locale} /> : null}
    </section>
  );
}
