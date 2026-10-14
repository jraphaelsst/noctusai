/**
 * `/itens` -- the items organ (SKU catalog, units, fiscal data, CSV import).
 * `canWrite` is the UX gate only; the server enforces org-admin on every write.
 */
import * as React from "react";
import { ItemEditor, ItemsTable } from "@noctusai/lib";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";

import { itemsHooks } from "@/lib/erpHooks";

export default function Itens() {
  const isAdmin = useIsOrgAdmin();
  // `undefined` = list; `null` = new item; an id = edit that item.
  const [editing, setEditing] = React.useState<string | null | undefined>(undefined);

  if (editing !== undefined) {
    return (
      <ItemEditor hooks={itemsHooks} itemId={editing} onSaved={() => setEditing(undefined)} onCancel={() => setEditing(undefined)} />
    );
  }
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-foreground">Itens</h1>
      <ItemsTable hooks={itemsHooks} canWrite={isAdmin} onCreate={() => setEditing(null)} onSelect={(item) => setEditing(item.id)} />
    </div>
  );
}
