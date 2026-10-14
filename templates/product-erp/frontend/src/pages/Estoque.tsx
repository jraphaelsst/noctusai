/**
 * `/estoque` -- the inventory organ (balances, low stock, valuation, warehouses; moving-average cost).
 * `canWrite` is the UX gate only; the server enforces org-admin on every write.
 */
import {
  LowStockAlerts,
  StockBalancesTable,
  ValuationTile,
  WarehousesManager,
} from "@noctusai/lib";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";

import { inventoryHooks } from "@/lib/erpHooks";

export default function Estoque() {
  const isAdmin = useIsOrgAdmin();
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-foreground">Estoque</h1>
      <div className="grid gap-4 lg:grid-cols-2">
        <ValuationTile hooks={inventoryHooks} />
        <LowStockAlerts hooks={inventoryHooks} />
      </div>
      <StockBalancesTable hooks={inventoryHooks} canWrite={isAdmin} />
      <WarehousesManager hooks={inventoryHooks} canWrite={isAdmin} />
    </div>
  );
}
