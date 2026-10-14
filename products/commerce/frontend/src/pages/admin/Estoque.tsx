/**
 * `/admin/estoque` — stock per warehouse: balances (count / transfer for admins, kardex drill-down), warehouses,
 * low-stock alerts and valuation. Item names come from the items catalog (the inventory organ only knows ids).
 * Item names are fetched for the VISIBLE ids only (`useItemLabels`).
 */
import * as React from "react";
import { KardexView, LowStockAlerts, StockBalancesTable, ValuationTile, WarehousesManager } from "@noctusai/lib";
import { Button, Tabs, TabsContent, TabsList, TabsTrigger, useIsOrgAdmin } from "@noctusai/lib/design-system";

import { AdminFrame } from "@/components/AdminFrame";
import { useItemLabels } from "@/hooks/useItemLabels";
import { staffInventory } from "@/lib/backoffice";
import { usePageT } from "@/lib/i18n";

function InventoryBody() {
  const { t } = usePageT();
  const isAdmin = useIsOrgAdmin();
  const itemLabel = useItemLabels();
  const [kardex, setKardex] = React.useState<{ itemId: string; warehouseId: string } | null>(null);

  if (kardex) {
    return (
      <div className="space-y-3">
        <Button variant="ghost" onClick={() => setKardex(null)}>{t("admin.inventory_back")}</Button>
        <KardexView hooks={staffInventory} itemLabel={itemLabel} itemId={kardex.itemId} warehouseId={kardex.warehouseId} />
      </div>
    );
  }
  return (
    <Tabs defaultValue="balances">
      <TabsList>
        <TabsTrigger value="balances">{t("admin.inventory_tab_balances")}</TabsTrigger>
        <TabsTrigger value="warehouses">{t("admin.inventory_tab_warehouses")}</TabsTrigger>
        <TabsTrigger value="alerts">{t("admin.inventory_tab_alerts")}</TabsTrigger>
      </TabsList>
      <TabsContent value="balances">
        <StockBalancesTable
          hooks={staffInventory}
          itemLabel={itemLabel}
          canWrite={isAdmin}
          onOpenKardex={(itemId, warehouseId) => setKardex({ itemId, warehouseId })}
        />
      </TabsContent>
      <TabsContent value="warehouses">
        <WarehousesManager hooks={staffInventory} canWrite={isAdmin} />
      </TabsContent>
      <TabsContent value="alerts">
        <div className="space-y-6">
          <ValuationTile hooks={staffInventory} />
          <LowStockAlerts hooks={staffInventory} itemLabel={itemLabel} onOpenItem={(itemId, warehouseId) => setKardex({ itemId, warehouseId })} />
        </div>
      </TabsContent>
    </Tabs>
  );
}

export default function Estoque() {
  return (
    <AdminFrame titleKey="admin.inventory_title" introKey="admin.inventory_intro">
      <InventoryBody />
    </AdminFrame>
  );
}
