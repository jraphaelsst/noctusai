/** `<LowStockAlerts/>` — items whose available stock is at or below their minimum. */
import { Badge, EmptyState, ListSkeleton, RefreshingBar, RetryError } from './controls';
import { formatQty, shortId } from './format';
import { errorMessage } from './hooks';
import { defaultInventoryT } from './i18n';
import type { InventoryOrganProps } from './shared';

export interface LowStockAlertsProps extends InventoryOrganProps {
  onOpenItem?: (itemId: string, warehouseId: string) => void;
}

export function LowStockAlerts({ hooks, t = defaultInventoryT, locale, itemLabel = shortId, onOpenItem }: LowStockAlertsProps) {
  const low = hooks.useLowStock();
  const warehouses = hooks.useWarehouses();
  if (low.showSkeleton) return <ListSkeleton rows={3} />;
  if (low.isError && !low.data) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(low.error)}`} onRetry={() => low.refetch()} retryLabel={t('common.retry')} />;
  }
  const rows = low.data ?? [];
  const whName = new Map((warehouses.data ?? []).map((w) => [w.id, w.name]));
  return (
    <section className="space-y-2" aria-busy={low.isRefreshing} aria-label={t('low.title')}>
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-semibold">{t('low.title')}</h3>
        {rows.length > 0 ? <Badge variant="destructive">{t('low.summary', { count: rows.length })}</Badge> : null}
        <RefreshingBar active={low.isRefreshing} label={t('common.refreshing')} />
      </div>
      {rows.length === 0 ? (
        <EmptyState message={t('low.empty')} />
      ) : (
        <ul className="divide-y rounded-md border">
          {rows.map((r) => {
            const body = (
              <>
                <span className="font-medium">{itemLabel(r.item_id)}</span>
                <span className="text-xs text-muted-foreground">{whName.get(r.warehouse_id) ?? shortId(r.warehouse_id)}</span>
                <span className="ml-auto text-xs">{t('low.available', { available: formatQty(r.available, locale), min: formatQty(r.min_qty, locale) })}</span>
              </>
            );
            return (
              <li key={`${r.item_id}:${r.warehouse_id}`} data-testid="low-stock-row">
                {onOpenItem ? (
                  <button type="button" className="flex w-full items-center gap-2 p-3 text-left text-sm hover:bg-accent" onClick={() => onOpenItem(r.item_id, r.warehouse_id)}>{body}</button>
                ) : (
                  <div className="flex items-center gap-2 p-3 text-sm">{body}</div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
