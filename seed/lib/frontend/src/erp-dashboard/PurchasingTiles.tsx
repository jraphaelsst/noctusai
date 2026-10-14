/** `<ErpPurchasingTiles/>` — purchase orders awaiting approval and awaiting receipt. Needs the purchasing hooks. */
import type { PurchasingHooks } from '../purchasing/hooks';
import { ErpStat, ErpTileSection, type ErpTileGroupProps } from './shared';

export interface ErpPurchasingTilesProps extends ErpTileGroupProps {
  hooks: PurchasingHooks;
}

export function ErpPurchasingTiles({ hooks, t }: ErpPurchasingTilesProps) {
  // `pagination.total` is exact whatever the page size, so one row per status is enough.
  const draft = hooks.usePurchaseOrders({ status: 'draft', page: 1, page_size: 1 });
  const approved = hooks.usePurchaseOrders({ status: 'approved', page: 1, page_size: 1 });
  const sent = hooks.usePurchaseOrders({ status: 'sent', page: 1, page_size: 1 });
  const partial = hooks.usePurchaseOrders({ status: 'partially_received', page: 1, page_size: 1 });
  const receiptQueries = [approved, sent, partial];
  const receiptReady = receiptQueries.every((q) => q.data);
  const receiptTotal = receiptQueries.reduce((s, q) => s + (q.data?.pagination.total ?? 0), 0);
  // One query stands for the group's loading/error/refresh state: skeleton while any is first-loading.
  const receipt = {
    showSkeleton: receiptQueries.some((q) => q.showSkeleton),
    isRefreshing: receiptQueries.some((q) => q.isRefreshing),
    isError: receiptQueries.some((q) => q.isError && !q.data),
    error: receiptQueries.find((q) => q.isError)?.error,
    refetch: () => Promise.all(receiptQueries.map((q) => q.refetch())),
  };
  return (
    <ErpTileSection title={t('purchasing.title')} testId="erp-purchasing">
      <ErpStat testId="erp-po-approval" t={t} query={draft} label={t('purchasing.awaiting_approval')} hint={t('purchasing.awaiting_approval_hint')}
        value={draft.data ? String(draft.data.pagination.total) : '—'} />
      <ErpStat testId="erp-po-receipt" t={t} query={receipt} label={t('purchasing.awaiting_receipt')} hint={t('purchasing.awaiting_receipt_hint')}
        value={receiptReady ? String(receiptTotal) : '—'} />
    </ErpTileSection>
  );
}
