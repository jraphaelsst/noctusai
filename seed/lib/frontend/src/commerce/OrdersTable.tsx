/** `<OrdersTable/>` — paginated staff order list with a status filter (CONTRACT §3 `GET /api/commerce/orders`). */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { EmptyState, ListSkeleton, RefreshingBar, RetryError, Select } from './controls';
import { useCommerceT } from './i18n';
import { formatCents, formatDateTime } from './format';
import { errorMessage, type CommerceHooks } from './hooks';
import { OrderStatusChip } from './OrderStatusChip';
import { ORDER_STATUSES, type Order, type OrderStatus } from './types';

export interface OrdersTableProps {
  hooks: CommerceHooks;
  locale?: string;
  onSelect?: (order: Order) => void;
}

export function OrdersTable({ hooks, locale, onSelect }: OrdersTableProps) {
  const { t, locale: loc } = useCommerceT(locale);
  const [status, setStatus] = React.useState<OrderStatus | ''>('');
  const [page, setPage] = React.useState(1);
  const orders = hooks.useOrders({ status, page });

  if (orders.showSkeleton) return <ListSkeleton rows={6} />;
  if (orders.isError && !orders.data) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(orders.error)}`} onRetry={() => orders.refetch()} retryLabel={t('common.retry')} />;
  }
  const rows = orders.data?.data ?? [];
  const pg = orders.data?.pagination;
  const totalPages = pg ? (pg.total_pages ?? Math.max(1, Math.ceil(pg.total / pg.page_size))) : 1;

  return (
    <section className="space-y-3" aria-busy={orders.isRefreshing}>
      <div className="flex items-center gap-2">
        <label className="text-sm" htmlFor="orders-status-filter">{t('orders.filter_status')}</label>
        <Select
          id="orders-status-filter"
          className="w-48"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as OrderStatus | '');
            setPage(1);
          }}
        >
          <option value="">{t('common.all')}</option>
          {ORDER_STATUSES.map((s) => (
            <option key={s} value={s}>{t(`order_status.${s}`)}</option>
          ))}
        </Select>
      </div>
      <RefreshingBar active={orders.isRefreshing} label={t('common.refreshing')} />
      {rows.length === 0 ? (
        <EmptyState message={t('orders.empty')} />
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-xs text-muted-foreground">
              <th className="p-2">{t('orders.col_date')}</th>
              <th className="p-2">{t('orders.col_status')}</th>
              <th className="p-2">{t('orders.col_method')}</th>
              <th className="p-2 text-right">{t('orders.col_total')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((o) => (
              <tr
                key={o.id}
                className={onSelect ? 'cursor-pointer border-b hover:bg-accent' : 'border-b'}
                onClick={onSelect ? () => onSelect(o) : undefined}
              >
                <td className="p-2">{formatDateTime(o.created_at, loc)}</td>
                <td className="p-2"><OrderStatusChip status={o.status} locale={locale} /></td>
                <td className="p-2">{o.payment_method ? t(`payment.${o.payment_method}`) : '—'}</td>
                <td className="p-2 text-right">{formatCents(o.total_cents, o.currency, loc)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {totalPages > 1 ? (
        <div className="flex items-center justify-end gap-2 text-sm">
          <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>{t('common.previous')}</Button>
          <span>{page} / {totalPages}</span>
          <Button size="sm" variant="outline" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>{t('common.next')}</Button>
        </div>
      ) : null}
    </section>
  );
}
