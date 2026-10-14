/**
 * `/admin/itens` — the SKU catalog with fiscal data: `ItemsTable` (list, filters, archive, CSV export), the
 * `ItemEditor` (create / edit in place), the `ItemCategoryManager` tree and `ItemsImport`. Writes are for org
 * admins (UX hint; the server enforces): staff get a read-only list and tree and no import.
 */
import * as React from "react";
import { ItemCategoryManager, ItemEditor, ItemsImport, ItemsTable } from "@noctusai/lib";
import { Button, Tabs, TabsContent, TabsList, TabsTrigger, useIsOrgAdmin } from "@noctusai/lib/design-system";

import { AdminFrame } from "@/components/AdminFrame";
import { staffItems } from "@/lib/backoffice";
import { usePageT } from "@/lib/i18n";

/** `null` = the list; `"new"` = the create form; otherwise the id being edited. */
type Editing = string | null;

function ItemsBody() {
  const { t } = usePageT();
  const isAdmin = useIsOrgAdmin();
  const [editing, setEditing] = React.useState<Editing>(null);

  if (editing !== null) {
    return (
      <div className="space-y-3">
        <Button variant="ghost" onClick={() => setEditing(null)}>{t("admin.items_back")}</Button>
        <ItemEditor
          hooks={staffItems}
          itemId={editing === "new" ? null : editing}
          onSaved={() => setEditing(null)}
          onCancel={() => setEditing(null)}
        />
      </div>
    );
  }
  return (
    <Tabs defaultValue="list">
      <TabsList>
        <TabsTrigger value="list">{t("admin.items_tab_list")}</TabsTrigger>
        <TabsTrigger value="categories">{t("admin.items_tab_categories")}</TabsTrigger>
        {isAdmin ? <TabsTrigger value="import">{t("admin.items_tab_import")}</TabsTrigger> : null}
      </TabsList>
      <TabsContent value="list">
        <ItemsTable
          hooks={staffItems}
          canWrite={isAdmin}
          onCreate={isAdmin ? () => setEditing("new") : undefined}
          onSelect={isAdmin ? (item) => setEditing(item.id) : undefined}
        />
      </TabsContent>
      <TabsContent value="categories">
        <ItemCategoryManager hooks={staffItems} canWrite={isAdmin} />
      </TabsContent>
      {isAdmin ? (
        <TabsContent value="import">
          <ItemsImport hooks={staffItems} />
        </TabsContent>
      ) : null}
    </Tabs>
  );
}

export default function Itens() {
  return (
    <AdminFrame titleKey="admin.items_title" introKey="admin.items_intro">
      <ItemsBody />
    </AdminFrame>
  );
}
