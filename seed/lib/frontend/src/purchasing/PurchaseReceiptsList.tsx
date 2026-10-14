/** `<PurchaseReceiptsList/>` — receipts (all, or one order's) with their landed amounts and posting state (stock + payables). */
import * as React from 'react';
import { Badge, Button, EmptyState, FormError, ListSkeleton, RefreshingBar, RetryError } from './controls';
import { formatCents, formatDate } from './format';
import { errorMessage, purchasingErrorMessage } from './hooks';
import { defaultPurchasingT } from './i18n';
import type { PurchasingOrganProps } from './shared';

export interface PurchaseReceiptsListProps extends PurchasingOrganProps {
  orderId?: string;
  /** Only receipts whose stock/payable posting is still open. */
  pendingOnly?: boolean;
  /** Shows the repost action (the API enforces admin anyway). */
  canWrite?: boolean;
}

export function PurchaseReceiptsList({ hooks, t = defaultPurchasingT, locale, orderId, pendingOnly = false, canWrite = false }: PurchaseReceiptsListProps) {
  const [page, setPage] = React.useState(1);
  const [err, setErr] = React.useState<string | null>(null);
  const receipts = hooks.usePurchaseReceipts({ order_id: orderId, pending: pendingOnly || undefined, page });
  const { repost } = hooks.useReceiptMutations();

  if (receipts.showSkeleton) return <ListSkeleton rows={4} />;
  if (receipts.isError && !receipts.data) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(receipts.error)}`} onRetry={() => receipts.refetch()} retryLabel={t('common.retry')} />;
  }
  const rows = receipts.data?.data ?? [];
  const pg = receipts.data?.pagination;
  const totalPages = pg ? (pg.total_pages ?? Math.max(1, Math.ceil(pg.total / pg.page_size))) : 1;

  async function doRepost(id: string) {
    setErr(null);
    try {
      await repost.mutateAsync(id);
    } catch (e) {
      setErr(purchasingErrorMessage(e, t));
    }
  }

  return (
    <section className="space-y-3" aria-busy={receipts.isRefreshing} aria-label={t('receipts.title')}>
      <RefreshingBar active={receipts.isRefreshing} label={t('common.refreshing')} />
      {rows.length === 0 ? (
        <EmptyState message={t('receipts.empty')} />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th className="py-2">{t('receipts.no')}</th>
                <th>{t('receipts.date')}</th>
                <th className="text-right">{t('receipts.goods')}</th>
                <th className="text-right">{t('receipts.adjustment')}</th>
                <th className="text-right">{t('receipts.total')}</th>
                <th>{t('receipts.posting')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const posted = !!(r.stock_posted_at && r.finance_posted_at);
                return (
                  <tr key={r.id} className="border-b" data-testid="receipt-row">
                    <td className="py-2">{r.receipt_no}</td>
                    <td>{formatDate(r.received_on)}</td>
                    <td className="text-right">{formatCents(r.goods_cents, 'BRL', locale)}</td>
                    <td className="text-right">{formatCents(r.adjustment_cents, 'BRL', locale)}</td>
                    <td className="text-right font-medium">{formatCents(r.total_cents, 'BRL', locale)}</td>
                    <td className="space-x-2">
                      <Badge variant={posted ? 'default' : 'destructive'}>{posted ? t('receipts.posted') : t('receipts.pending')}</Badge>
                      {r.posting_error ? <span className="text-xs text-muted-foreground">{r.posting_error}</span> : null}
                      {!posted && canWrite ? (
                        <Button size="sm" variant="outline" disabled={repost.isPending} onClick={() => doRepost(r.id)}>{t('receipts.repost')}</Button>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <FormError message={err} />
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
