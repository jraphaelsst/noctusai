/** `<ValuationTile/>` — total stock value at moving-average cost (Σ on hand × average cost). */
import { Card, EmptyState, ListSkeleton, RefreshingBar, RetryError } from './controls';
import { formatCents } from './format';
import { errorMessage } from './hooks';
import { defaultInventoryT } from './i18n';
import type { InventoryOrganProps } from './shared';

export interface ValuationTileProps extends InventoryOrganProps {
  warehouseId?: string;
}

export function ValuationTile({ hooks, t = defaultInventoryT, locale, warehouseId }: ValuationTileProps) {
  const v = hooks.useValuation(warehouseId);
  if (v.showSkeleton) return <ListSkeleton rows={1} />;
  if (v.isError && !v.data) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(v.error)}`} onRetry={() => v.refetch()} retryLabel={t('common.retry')} />;
  }
  const d = v.data;
  return (
    <Card aria-busy={v.isRefreshing} data-testid="valuation-tile">
      <p className="text-xs text-muted-foreground">{t('valuation.title')} · {t('valuation.method')}</p>
      {!d || d.items === 0 ? (
        <EmptyState message={t('valuation.empty')} />
      ) : (
        <>
          <p className="text-2xl font-semibold" data-testid="valuation-total">{formatCents(d.total_cents, 'BRL', locale)}</p>
          <p className="text-xs text-muted-foreground">{t('valuation.items', { count: d.items })}</p>
        </>
      )}
      <RefreshingBar active={v.isRefreshing} label={t('common.refreshing')} />
    </Card>
  );
}
