/**
 * `<OrderStatusPage/>` — the buyer's order page by opaque token (CONTRACT §4
 * `GET /api/storefront/orders/{token}`). Polls while `pending_payment`
 * (`refetchInterval`, stops on any other status; a poll shows `isRefreshing`,
 * never a skeleton). Pix: QR image + copy-paste code; other methods: link to
 * the gateway `checkout_url`. Expired / failed: message + "gerar novo pagamento"
 * (CONTRACT P4 §2.4 / D35 — `POST /storefront/orders/{token}/payment`, the buyer
 * picks the method; the page refreshes to the new charge). A host that wants its
 * own flow passes `onNewPayment` instead. A card order paid in parcelas shows
 * what was actually charged (interest included).
 */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { EmptyState, FormError, ListSkeleton, RefreshingBar, RetryError } from './controls';
import { useCommerceT } from './i18n';
import { formatCents, formatDateTime } from './format';
import { apiErrorStatus, errorMessage, type CommerceHooks } from './hooks';
import { Select } from './controls';
import { OrderStatusChip } from './OrderStatusChip';
import { PAYMENT_METHODS, type PaymentMethod, type PublicOrder } from './types';

export interface OrderStatusPageProps {
  hooks: CommerceHooks;
  token: string;
  locale?: string;
  onNewPayment?: (order: PublicOrder) => void;
}

export function OrderStatusPage({ hooks, token, locale, onNewPayment }: OrderStatusPageProps) {
  const { t, locale: loc } = useCommerceT(locale);
  const order = hooks.usePublicOrder(token, { poll: true });
  const [copied, setCopied] = React.useState<'ok' | 'fail' | null>(null);
  const regenerate = hooks.useRegeneratePayment(token);
  const [newMethod, setNewMethod] = React.useState<PaymentMethod | null>(null);

  if (order.showSkeleton) return <ListSkeleton rows={4} />;
  if (apiErrorStatus(order.error) === 404) return <EmptyState message={t('orders.not_found')} />;
  if (order.isError && !order.data) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(order.error)}`} onRetry={() => order.refetch()} retryLabel={t('common.retry')} />;
  }
  const o = order.data;
  if (!o) return <EmptyState message={t('orders.not_found')} />;

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied('ok');
    } catch {
      setCopied('fail');
    }
  }

  const qr = o.pix_qr;
  const method: PaymentMethod = newMethod ?? o.payment_method ?? 'pix';
  const newPaymentControl = onNewPayment ? (
    <Button variant="outline" onClick={() => onNewPayment(o)}>{t('status.new_payment')}</Button>
  ) : (
    <div className="flex flex-wrap items-center gap-2">
      <Select aria-label={t('status.regen_method')} value={method} disabled={regenerate.isPending} onChange={(e) => setNewMethod(e.target.value as PaymentMethod)}>
        {PAYMENT_METHODS.map((m) => <option key={m} value={m}>{t(`payment.${m}`)}</option>)}
      </Select>
      <Button
        variant="outline"
        disabled={regenerate.isPending}
        onClick={async () => {
          try {
            await regenerate.mutateAsync({ payment_method: method });
          } catch {
            // Surfaced below via `regenerate.error` (429 muitas_tentativas, 409 pedido_alterado, ...) — not swallowed.
          }
        }}
      >
        {regenerate.isPending ? t('status.regenerating') : t('status.new_payment')}
      </Button>
      {regenerate.isError ? <FormError message={errorMessage(regenerate.error)} /> : null}
    </div>
  );
  return (
    <article className="mx-auto max-w-xl space-y-4" aria-busy={order.isRefreshing}>
      <header className="flex items-center gap-3">
        <h1 className="text-xl font-semibold">{t('status.title')}</h1>
        <OrderStatusChip status={o.status} locale={locale} />
      </header>
      <RefreshingBar active={order.isRefreshing} label={t('status.checking')} />

      {o.status === 'pending_payment' ? (
        <section className="space-y-3 rounded-md border p-4" aria-label={t('status.pay')}>
          <p className="text-sm" role="status">{t('status.waiting')}</p>
          {o.payment_method === 'pix' && qr ? (
            <div className="space-y-2">
              {qr.encoded_image ? (
                <img src={`data:image/png;base64,${qr.encoded_image}`} alt={t('status.pix_qr_alt')} className="mx-auto h-48 w-48" />
              ) : null}
              {qr.payload ? (
                <>
                  <textarea readOnly aria-label={t('status.pix_code')} value={qr.payload} rows={3} className="w-full rounded border p-2 font-mono text-xs" />
                  <Button variant="outline" onClick={() => copy(qr.payload!)}>{t('status.copy_pix')}</Button>
                  {copied === 'ok' ? <span role="status" className="ml-2 text-sm text-green-600">{t('status.copied')}</span> : null}
                  {copied === 'fail' ? <span role="alert" className="ml-2 text-sm text-destructive">{t('status.copy_failed')}</span> : null}
                </>
              ) : null}
              {o.expires_at ? <p className="text-xs text-muted-foreground">{t('status.expires_at')} {formatDateTime(o.expires_at, loc)}</p> : null}
            </div>
          ) : null}
          {o.checkout_url ? (
            <a href={o.checkout_url} target="_blank" rel="noopener noreferrer" className="inline-block rounded-md border px-3 py-1.5 text-sm underline">
              {t('status.open_checkout')}
            </a>
          ) : null}
        </section>
      ) : null}

      {o.status === 'paid' ? <p role="status" className="rounded-md border border-green-500/40 bg-green-500/10 p-3 text-sm">{t('status.paid')}</p> : null}
      {o.status === 'expired' ? (
        <div className="space-y-2 rounded-md border p-3">
          <p role="status" className="text-sm">{t('status.expired')}</p>
          {newPaymentControl}
        </div>
      ) : null}
      {o.status === 'failed' ? (
        <div className="space-y-2 rounded-md border p-3">
          <FormError message={t('status.failed')} />
          {newPaymentControl}
        </div>
      ) : null}
      {o.status === 'cancelled' ? <p role="status" className="text-sm">{t('status.cancelled')}</p> : null}
      {o.status === 'refunded' ? <p role="status" className="text-sm">{t('status.refunded')}</p> : null}
      {o.status === 'chargeback' ? <p role="status" className="text-sm">{t('status.chargeback')}</p> : null}

      <ul className="divide-y rounded-md border text-sm">
        {o.items.map((i, idx) => (
          <li key={idx} className="flex justify-between p-2">
            <span>{i.qty}× {i.title}</span>
            <span>{formatCents(i.total_cents, o.currency, loc)}</span>
          </li>
        ))}
      </ul>
      <p className="text-right text-base font-semibold">{t('cart.total')}: {formatCents(o.total_cents, o.currency, loc)}</p>
      {o.payment_method === 'credit_card' && (o.installment_count ?? 1) > 1 && o.charged_cents ? (
        <p className="text-right text-sm text-muted-foreground" data-testid="charged-total">
          {t('status.charged', { total: formatCents(o.charged_cents, o.currency, loc), count: o.installment_count ?? 1 })}
        </p>
      ) : null}
    </article>
  );
}
