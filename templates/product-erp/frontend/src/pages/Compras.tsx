/**
 * `/compras` -- the purchasing organ (purchase orders -> approval -> receipt -> stock in + payable).
 * `canWrite` is the UX gate only; the server enforces org-admin on every write.
 */
import * as React from "react";
import { PurchaseOrderEditor, PurchaseOrdersTable } from "@noctusai/lib";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";

import { inventoryHooks, itemsHooks, partiesHooks, usePurchasingHooks } from "@/lib/erpHooks";

export default function Compras() {
  const isAdmin = useIsOrgAdmin();
  const purchasing = usePurchasingHooks();
  // `undefined` = list; `null` = new order; an id = edit that draft.
  const [editing, setEditing] = React.useState<string | null | undefined>(undefined);

  if (editing !== undefined) {
    return (
      <PurchaseOrderEditor
        hooks={purchasing}
        orderId={editing}
        partiesHooks={partiesHooks}
        itemsHooks={itemsHooks}
        inventoryHooks={inventoryHooks}
        onSaved={() => setEditing(undefined)}
        onCancel={() => setEditing(undefined)}
      />
    );
  }
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-foreground">Compras</h1>
      <PurchaseOrdersTable hooks={purchasing} canWrite={isAdmin} onNew={() => setEditing(null)} />
    </div>
  );
}
