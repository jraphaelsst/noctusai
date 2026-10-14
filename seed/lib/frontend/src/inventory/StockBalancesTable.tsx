/** `<StockBalancesTable/>` — balances by item × warehouse (on hand / reserved / available / average cost / value). */
import * as React from 'react';
import { Badge, Button, EmptyState, ListSkeleton, RefreshingBar, RetryError, Select } from './controls';
import { formatCents, formatQty, shortId } from './format';
import { errorMessage } from './hooks';
import { defaultInventoryT } from './i18n';
import type { InventoryOrganProps } from './shared';
import { StockAdjustDialog } from './StockAdjustDialog';
import { TransferDialog } from './TransferDialog';
import type { StockBalance } from './types';

export interface StockBalancesTableProps extends InventoryOrganProps {
  /** Scope to one item (e.g. on an item page). */
  itemId?: string;
  /** Show the count / transfer row actions (the host decides from the user's role; the API enforces admin anyway). */
  canWrite?: boolean;
  onOpenKardex?: (itemId: string, warehouseId: string) => void;
}

export function StockBalancesTable({ hooks, t = defaultInventoryT, locale, itemLabel = shortId, itemId, canWrite = false, onOpenKardex }: StockBalancesTableProps) {
  const [warehouseId, setWarehouseId] = React.useState('');
  const [includeZero, setIncludeZero] = React.useState(false);
  const [page, setPage] = React.useState(1);
  const [adjusting, setAdjusting] = React.useState<StockBalance | null>(null);
  const [transferring, setTransferring] = React.useState<StockBalance | null>(null);

  const warehouses = hooks.useWarehouses();
  const balances = hooks.useBalances({ item_id: itemId, warehouse_id: warehouseId || undefined, include_zero: includeZero, page });
  const whName = React.useMemo(() => new Map((warehouses.data ?? []).map((w) => [w.id, w.name])), [warehouses.data]);

  if (balances.showSkeleton) return <ListSkeleton rows={6} />;
  if (balances.isError && !balances.data) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(balances.error)}`} onRetry={() => balances.refetch()} retryLabel={t('common.retry')} />;
  }
  const rows = balances.data?.data ?? [];
  const pg = balances.data?.pagination;
  const totalPages = pg ? (pg.total_pages ?? Math.max(1, Math.ceil(pg.total / pg.page_size))) : 1;

  return (
    <section className="space-y-3" aria-busy={balances.isRefreshing} aria-label={t('balances.title')}>
      <div className="flex flex-wrap items-center gap-3">
        <Select aria-label={t('balances.warehouse')} value={warehouseId} onChange={(e) => { setWarehouseId(e.target.value); setPage(1); }} className="w-56">
          <option value="">{t('common.all_warehouses')}</option>
          {(warehouses.data ?? []).map((w) => (
            <option key={w.id} value={w.id}>{w.name}</option>
          ))}
        </Select>
        <label className="flex items-center gap-1 text-xs">
          <input type="checkbox" checked={includeZero} onChange={(e) => { setIncludeZero(e.target.checked); setPage(1); }} />
          {t('balances.show_zero')}
        </label>
        <RefreshingBar active={balances.isRefreshing} label={t('common.refreshing')} />
      </div>
      {rows.length === 0 ? (
        <EmptyState message={t('balances.empty')} />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th className="py-2">{t('balances.item')}</th>
                <th>{t('balances.warehouse')}</th>
                <th className="text-right">{t('balances.on_hand')}</th>
                <th className="text-right">{t('balances.reserved')}</th>
                <th className="text-right">{t('balances.available')}</th>
                <th className="text-right">{t('balances.avg_cost')}</th>
                <th className="text-right">{t('balances.value')}</th>
                <th className="text-right">{t('balances.min')}</th>
                <th>{t('balances.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={`${r.item_id}:${r.warehouse_id}`} className="border-b" data-testid="balance-row">
                  <td className="py-2">{itemLabel(r.item_id)}</td>
                  <td>{whName.get(r.warehouse_id) ?? shortId(r.warehouse_id)}</td>
                  <td className="text-right">{formatQty(r.on_hand, locale)}</td>
                  <td className="text-right">{formatQty(r.reserved, locale)}</td>
                  <td className="text-right font-medium">{formatQty(r.available, locale)}</td>
                  <td className="text-right">{formatCents(r.avg_cost_cents, 'BRL', locale)}</td>
                  <td className="text-right">{formatCents(r.value_cents, 'BRL', locale)}</td>
                  <td className="text-right">
                    {r.min_qty != null ? formatQty(r.min_qty, locale) : '—'} {r.low_stock ? <Badge variant="destructive">{t('balances.low')}</Badge> : null}
                  </td>
                  <td className="space-x-1 whitespace-nowrap">
                    {onOpenKardex ? <Button size="sm" variant="ghost" onClick={() => onOpenKardex(r.item_id, r.warehouse_id)}>{t('balances.kardex')}</Button> : null}
                    {canWrite ? (
                      <>
                        <Button size="sm" variant="ghost" onClick={() => setAdjusting(r)}>{t('balances.adjust')}</Button>
                        <Button size="sm" variant="ghost" onClick={() => setTransferring(r)}>{t('balances.transfer')}</Button>
                      </>
                    ) : null}
                  </td>
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
      {adjusting ? (
        <StockAdjustDialog hooks={hooks} t={t} locale={locale} itemLabel={itemLabel} open itemId={adjusting.item_id} warehouseId={adjusting.warehouse_id} currentOnHand={adjusting.on_hand} onClose={() => setAdjusting(null)} />
      ) : null}
      {transferring ? (
        <TransferDialog hooks={hooks} t={t} locale={locale} itemLabel={itemLabel} open itemId={transferring.item_id} fromWarehouseId={transferring.warehouse_id} available={transferring.available} onClose={() => setTransferring(null)} />
      ) : null}
    </section>
  );
}
