/** `<PurchaseOrdersTable/>` — purchase orders with status filter, supplier/number search and paging. */
import * as React from 'react';
import { Badge, Button, EmptyState, Input, ListSkeleton, RefreshingBar, RetryError, Select } from './controls';
import { formatCents, formatDate } from './format';
import { errorMessage } from './hooks';
import { defaultPurchasingT } from './i18n';
import type { PurchasingOrganProps } from './shared';
import { PURCHASE_ORDER_STATUSES, type PurchaseOrder, type PurchaseOrderStatus } from './types';

export interface PurchaseOrdersTableProps extends PurchasingOrganProps {
  onOpen?: (order: PurchaseOrder) => void;
  /** Shows the "new order" button (the host decides from the user's role; the API enforces admin anyway). */
  canWrite?: boolean;
  onNew?: () => void;
  initialStatus?: PurchaseOrderStatus | '';
}

const VARIANT: Record<PurchaseOrderStatus, 'default' | 'muted' | 'outline' | 'destructive'> = {
  draft: 'muted',
  approved: 'outline',
  sent: 'outline',
  partially_received: 'default',
  received: 'default',
  cancelled: 'destructive',
};

export function PurchaseOrdersTable({ hooks, t = defaultPurchasingT, locale, onOpen, canWrite = false, onNew, initialStatus = '' }: PurchaseOrdersTableProps) {
  const [status, setStatus] = React.useState<PurchaseOrderStatus | ''>(initialStatus);
  const [q, setQ] = React.useState('');
  const [page, setPage] = React.useState(1);
  const orders = hooks.usePurchaseOrders({ status, q: q.trim() || undefined, page });

  if (orders.showSkeleton) return <ListSkeleton rows={6} />;
  if (orders.isError && !orders.data) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(orders.error)}`} onRetry={() => orders.refetch()} retryLabel={t('common.retry')} />;
  }
  const rows = orders.data?.data ?? [];
  const pg = orders.data?.pagination;
  const totalPages = pg ? (pg.total_pages ?? Math.max(1, Math.ceil(pg.total / pg.page_size))) : 1;

  return (
    <section className="space-y-3" aria-busy={orders.isRefreshing} aria-label={t('orders.title')}>
      <div className="flex flex-wrap items-center gap-3">
        <Select aria-label={t('orders.status')} value={status} onChange={(e) => { setStatus(e.target.value as PurchaseOrderStatus | ''); setPage(1); }} className="w-56">
          <option value="">{t('common.all_statuses')}</option>
          {PURCHASE_ORDER_STATUSES.map((s) => (
            <option key={s} value={s}>{t(`status.${s}`)}</option>
          ))}
        </Select>
        <Input aria-label={t('common.search')} placeholder={t('common.search')} value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} className="w-64" />
        {canWrite && onNew ? <Button variant="primary" onClick={onNew}>{t('orders.new')}</Button> : null}
        <RefreshingBar active={orders.isRefreshing} label={t('common.refreshing')} />
      </div>
      {rows.length === 0 ? (
        <EmptyState message={t('orders.empty')} />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th className="py-2">{t('orders.number')}</th>
                <th>{t('orders.supplier')}</th>
                <th>{t('orders.status')}</th>
                <th className="text-right">{t('orders.total')}</th>
                <th>{t('orders.expected')}</th>
                {onOpen ? <th>{t('orders.actions')}</th> : null}
              </tr>
            </thead>
            <tbody>
              {rows.map((o) => (
                <tr key={o.id} className="border-b" data-testid="order-row">
                  <td className="py-2">#{o.number}</td>
                  <td>{o.supplier_name}</td>
                  <td><Badge variant={VARIANT[o.status]}>{t(`status.${o.status}`)}</Badge></td>
                  <td className="text-right">{formatCents(o.total_cents, 'BRL', locale)}</td>
                  <td>{formatDate(o.expected_date)}</td>
                  {onOpen ? <td><Button size="sm" variant="ghost" onClick={() => onOpen(o)}>{t('orders.open')}</Button></td> : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {totalPages > 1 ? (
        <div className="flex items-center justify-end gap-2 text-xs">
          <Button size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>{t('common.previous')}</Button>
          <span>{t('common.page', { page, pages: totalPages })}</span>
          <Button size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>{t('common.next')}</Button>
        </div>
      ) : null}
    </section>
  );
}
