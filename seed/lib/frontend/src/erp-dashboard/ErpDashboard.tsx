/**
 * `<ErpDashboard/>` — the ERP landing page: a COMPOSITION over the organ hooks the host mounted. No backend of
 * its own. A tile group renders only when the host passes that organ's hooks (organ-optional), so a product
 * that mounted finance + inventory shows exactly those two groups. Every tile loads and fails on its own.
 */
import type { ContractsHooks } from '../contracts/hooks';
import type { FinanceHooks } from '../finance/hooks';
import type { InventoryHooks } from '../inventory/hooks';
import type { PurchasingHooks } from '../purchasing/hooks';
import type { QuotesHooks } from '../quotes/hooks';
import { EmptyState } from '../organ-kit/controls';
import { ErpContractsTiles } from './ContractsTiles';
import { defaultErpDashboardT, type ErpDashboardTranslate } from './i18n';
import { ErpFinanceTiles } from './FinanceTiles';
import { ErpInventoryTiles } from './InventoryTiles';
import { ErpPurchasingTiles } from './PurchasingTiles';
import { ErpQuotesTiles } from './QuotesTiles';

export interface ErpDashboardProps {
  finance?: FinanceHooks;
  inventory?: InventoryHooks;
  purchasing?: PurchasingHooks;
  contracts?: ContractsHooks;
  quotes?: QuotesHooks;
  /** Translator override (defaults to the shipped pt-BR table). */
  t?: ErpDashboardTranslate;
  /** Reference date (tests inject it); default: now. */
  now?: Date;
  /** Optional deep link: called with the organ key (`finance` | `inventory` | …). */
  onNavigate?: (target: string) => void;
}

export function ErpDashboard({ finance, inventory, purchasing, contracts, quotes, t = defaultErpDashboardT, now, onNavigate }: ErpDashboardProps) {
  const common = { t, now, onNavigate };
  const any = !!(finance || inventory || purchasing || contracts || quotes);
  return (
    <div className="space-y-6" data-testid="erp-dashboard">
      <header>
        <h1 className="text-xl font-semibold">{t('dashboard.title')}</h1>
        <p className="text-sm text-muted-foreground">{t('dashboard.subtitle')}</p>
      </header>
      {!any ? <EmptyState message={t('dashboard.nothing_mounted')} /> : null}
      {finance ? <ErpFinanceTiles hooks={finance} {...common} /> : null}
      {inventory ? <ErpInventoryTiles hooks={inventory} {...common} /> : null}
      {purchasing ? <ErpPurchasingTiles hooks={purchasing} {...common} /> : null}
      {contracts ? <ErpContractsTiles hooks={contracts} {...common} /> : null}
      {quotes ? <ErpQuotesTiles hooks={quotes} {...common} /> : null}
    </div>
  );
}
