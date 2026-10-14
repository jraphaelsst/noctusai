/** `<ErpInventoryTiles/>` — low-stock count and stock valuation (moving-average cost). Needs the inventory hooks. */
import { formatCents } from '../organ-kit/money';
import type { InventoryHooks } from '../inventory/hooks';
import { ErpStat, ErpTileSection, type ErpTileGroupProps } from './shared';

export interface ErpInventoryTilesProps extends ErpTileGroupProps {
  hooks: InventoryHooks;
}

export function ErpInventoryTiles({ hooks, t, onNavigate }: ErpInventoryTilesProps) {
  const low = hooks.useLowStock();
  const valuation = hooks.useValuation();
  return (
    <ErpTileSection title={t('inventory.title')} testId="erp-inventory" openLabel={t('common.open')} onOpen={onNavigate ? () => onNavigate('inventory') : undefined}>
      <ErpStat testId="erp-low-stock" t={t} query={low} label={t('inventory.low_stock')} hint={t('inventory.low_stock_hint')}
        value={low.data ? String(low.data.length) : '—'} />
      <ErpStat testId="erp-valuation" t={t} query={valuation} label={t('inventory.valuation')}
        hint={valuation.data ? t('inventory.valuation_hint', { count: valuation.data.items }) : undefined}
        value={valuation.data ? formatCents(valuation.data.total_cents) : '—'} />
    </ErpTileSection>
  );
}
