/**
 * `/admin/estoque` — stock per warehouse: balances (count / transfer for admins, kardex drill-down), warehouses,
 * low-stock alerts and valuation. Item names come from the items catalog (the inventory organ only knows ids).
 *
 * NOC-REMEDIATE[commerce-parties-inventory-mount]: `/api/inventory` is not mounted in this host's backend yet, so
 * the page's `status_pagina` row (migration 019) is `desenvolvimento` and the organs show their error states
 * until the router is mounted — 2026-10-14. See `@/lib/backoffice`.
 * NOC-REMEDIATE[commerce-inventory-item-labels]: the id → name map covers the first page of the items list
 * (the organ's `itemLabel` seam is synchronous); an item beyond it falls back to a short id — lift a by-ids
 * lookup into the items organ — 2026-10-14.
 */
import * as React from "react";
import { KardexView, LowStockAlerts, StockBalancesTable, ValuationTile, WarehousesManager } from "@noctusai/lib";
import { Button, Tabs, TabsContent, TabsList, TabsTrigger, useIsOrgAdmin } from "@noctusai/lib/design-system";

import { AdminFrame } from "@/components/AdminFrame";
import { staffInventory, staffItems } from "@/lib/backoffice";
import { usePageT } from "@/lib/i18n";

function useItemLabel() {
  const items = staffItems.useItems({});
  return React.useMemo(() => {
    const names = new Map((items.data?.data ?? []).map((i) => [i.id, `${i.sku} · ${i.name}`]));
    return (id: string) => names.get(id) ?? id.slice(0, 8);
  }, [items.data]);
}

function InventoryBody() {
  const { t } = usePageT();
  const isAdmin = useIsOrgAdmin();
  const itemLabel = useItemLabel();
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
