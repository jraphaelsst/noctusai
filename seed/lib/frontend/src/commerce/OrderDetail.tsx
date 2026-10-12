/** `<OrderDetail/>` — one staff order: items, totals and the event timeline; cancel with an in-page confirm. */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { EmptyState, FormError, ListSkeleton, RefreshingBar, RetryError } from './controls';
import { useCommerceT } from './i18n';
import { formatCents, formatDateTime } from './format';
import { errorMessage, type CommerceHooks } from './hooks';
import { OrderStatusChip } from './OrderStatusChip';
import { ORDER_TRANSITIONS } from './types';

export interface OrderDetailProps {
  hooks: CommerceHooks;
  orderId: string;
  locale?: string;
}

export function OrderDetail({ hooks, orderId, locale }: OrderDetailProps) {
  const { t, locale: loc } = useCommerceT(locale);
  const order = hooks.useOrder(orderId);
  const cancel = hooks.useCancelOrder();
  const [confirming, setConfirming] = React.useState(false);

  if (order.showSkeleton) return <ListSkeleton rows={5} />;
  if (order.isError && !order.data) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(order.error)}`} onRetry={() => order.refetch()} retryLabel={t('common.retry')} />;
  }
  const o = order.data;
  if (!o) return <EmptyState message={t('orders.not_found')} />;
  const canCancel = ORDER_TRANSITIONS[o.status].includes('cancelled');
  const events = [...(o.events ?? [])].sort((a, b) => a.at.localeCompare(b.at));

  return (
    <section className="space-y-4" aria-busy={order.isRefreshing}>
      <RefreshingBar active={order.isRefreshing} label={t('common.refreshing')} />
      <header className="flex flex-wrap items-center gap-3">
        <h2 className="text-base font-semibold">{t('orders.detail_title')}</h2>
        <OrderStatusChip status={o.status} locale={locale} />
        <span className="text-xs text-muted-foreground">{formatDateTime(o.created_at, loc)}</span>
      </header>

      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-xs text-muted-foreground">
            <th className="p-2">{t('orders.col_item')}</th>
            <th className="p-2 text-right">{t('orders.col_qty')}</th>
            <th className="p-2 text-right">{t('orders.col_unit')}</th>
            <th className="p-2 text-right">{t('orders.col_total')}</th>
          </tr>
        </thead>
        <tbody>
          {(o.items ?? []).map((i) => (
            <tr key={i.id} className="border-b">
              <td className="p-2">{i.title_snapshot}</td>
              <td className="p-2 text-right">{i.qty}</td>
              <td className="p-2 text-right">{formatCents(i.unit_price_cents, o.currency, loc)}</td>
              <td className="p-2 text-right">{formatCents(i.total_cents, o.currency, loc)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <dl className="ml-auto w-64 space-y-1 text-sm">
        <div className="flex justify-between"><dt>{t('cart.subtotal')}</dt><dd>{formatCents(o.subtotal_cents, o.currency, loc)}</dd></div>
        {o.discount_cents > 0 ? (
          <div className="flex justify-between"><dt>{t('cart.discount')}</dt><dd>-{formatCents(o.discount_cents, o.currency, loc)}</dd></div>
        ) : null}
        <div className="flex justify-between font-semibold"><dt>{t('cart.total')}</dt><dd>{formatCents(o.total_cents, o.currency, loc)}</dd></div>
        {o.platform_fee_cents > 0 ? (
          <div className="flex justify-between text-xs text-muted-foreground"><dt>{t('orders.platform_fee')}</dt><dd>{formatCents(o.platform_fee_cents, o.currency, loc)}</dd></div>
        ) : null}
      </dl>

      <section aria-label={t('orders.timeline')}>
        <h3 className="mb-2 text-sm font-semibold">{t('orders.timeline')}</h3>
        {events.length === 0 ? (
          <EmptyState message={t('orders.timeline_empty')} />
        ) : (
          <ol className="space-y-2 border-l pl-4" data-testid="order-timeline">
            {events.map((e, idx) => (
              <li key={e.id ?? idx} className="text-sm">
                <span className="text-xs text-muted-foreground">{formatDateTime(e.at, loc)} · {t(`event_source.${e.source}`)}</span>
                <div>
                  {e.from_status ? `${t(`order_status.${e.from_status}`)} → ` : ''}
                  <strong>{t(`order_status.${e.to_status}`)}</strong>
                  {e.reason ? <span className="text-muted-foreground"> ({e.reason})</span> : null}
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>

      {canCancel ? (
        <div className="flex items-center gap-2">
          {confirming ? (
            <>
              <span className="text-sm">{t('orders.cancel_confirm')}</span>
              <Button
                variant="destructive"
                disabled={cancel.isPending}
                onClick={async () => {
                  try {
                    await cancel.mutateAsync(orderId);
                    setConfirming(false);
                  } catch {
                    // Surfaced via `cancel.error` below.
                  }
                }}
              >
                {t('orders.cancel')}
              </Button>
              <Button variant="ghost" onClick={() => setConfirming(false)}>{t('common.back')}</Button>
            </>
          ) : (
            <Button variant="outline" onClick={() => setConfirming(true)}>{t('orders.cancel')}</Button>
          )}
        </div>
      ) : null}
      <FormError message={cancel.error ? errorMessage(cancel.error) : null} />
    </section>
  );
}
