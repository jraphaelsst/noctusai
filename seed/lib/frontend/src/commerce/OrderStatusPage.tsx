/**
 * `<OrderStatusPage/>` — the buyer's order page by opaque token (CONTRACT §4
 * `GET /api/storefront/orders/{token}`). Polls while `pending_payment`
 * (`refetchInterval`, stops on any other status; a poll shows `isRefreshing`,
 * never a skeleton). Pix: QR image + copy-paste code; other methods: link to
 * the gateway `checkout_url`. Expired: message + "gerar novo pagamento"
 * (NOC-REMEDIATE[commerce-regenerate-payment]: no regenerate endpoint in the
 * P3 contract — the button calls `onNewPayment` when the host provides one,
 * otherwise it is disabled — 2026-10-12).
 */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { EmptyState, FormError, ListSkeleton, RefreshingBar, RetryError } from './controls';
import { useCommerceT } from './i18n';
import { formatCents, formatDateTime } from './format';
import { apiErrorStatus, errorMessage, type CommerceHooks } from './hooks';
import { OrderStatusChip } from './OrderStatusChip';
import type { PublicOrder } from './types';

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
          <Button variant="outline" disabled={!onNewPayment} onClick={() => onNewPayment?.(o)}>{t('status.new_payment')}</Button>
        </div>
      ) : null}
      {o.status === 'failed' ? <FormError message={t('status.failed')} /> : null}
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
    </article>
  );
}
