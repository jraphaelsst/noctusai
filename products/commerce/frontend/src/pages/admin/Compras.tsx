/**
 * `/admin/compras` — purchase orders to suppliers: the list, the draft editor (supplier from the parties organ, lines from
 * the items organ, the receiving warehouse from inventory), approve / send / cancel, receiving (stock in + payables) and the
 * org's approver list. Writes are for org admins (UX hint; the server enforces — and approval is decided from the org's
 * own `pur_approvers`, never a global permission).
 */
import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  financeKeys,
  inventoryKeys,
  PurchaseApproveButton,
  PurchaseApproversManager,
  PurchaseOrderEditor,
  PurchaseOrdersTable,
  PurchaseReceiptsList,
  PurchaseReceiveDialog,
} from "@noctusai/lib";
import { Button, Tabs, TabsContent, TabsList, TabsTrigger, useIsOrgAdmin } from "@noctusai/lib/design-system";

import { AdminFrame } from "@/components/AdminFrame";
import { staffInventory, staffItems, staffParties, staffPurchasing, staffTeam } from "@/lib/backoffice";
import { usePageT } from "@/lib/i18n";

/** The statuses a goods receipt can still be posted against. */
const RECEIVABLE = new Set(["approved", "sent", "partially_received"]);

/** `null` = the list; `"new"` = a new draft; otherwise the order being opened. */
type Open = string | null;

function OrderDetail({ id, onBack }: { id: string; onBack: () => void }) {
  const { t } = usePageT();
  const isAdmin = useIsOrgAdmin();
  const qc = useQueryClient();
  const order = staffPurchasing.usePurchaseOrder(id === "new" ? null : id);
  const settings = staffPurchasing.usePurchasingSettings();
  const [receiving, setReceiving] = React.useState(false);
  const current = order.data;

  return (
    <div className="space-y-4">
      <Button variant="ghost" onClick={onBack}>{t("admin.purchasing_back")}</Button>
      <PurchaseOrderEditor
        key={id}
        hooks={staffPurchasing}
        orderId={id === "new" ? null : id}
        partiesHooks={staffParties}
        itemsHooks={staffItems}
        inventoryHooks={staffInventory}
        onSaved={(saved) => {
          if (id === "new") onBack();
          else void qc.invalidateQueries({ queryKey: ["purchasing"] });
          return saved;
        }}
        onCancel={onBack}
      />
      {current ? (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <PurchaseApproveButton
              hooks={staffPurchasing}
              order={current}
              canManage={isAdmin}
              thresholdCents={settings.data?.approval_threshold_cents ?? null}
            />
            {isAdmin && RECEIVABLE.has(current.status) ? (
              <Button onClick={() => setReceiving(true)}>{t("admin.purchasing_receive")}</Button>
            ) : null}
          </div>
          <PurchaseReceiveDialog
            hooks={staffPurchasing}
            open={receiving}
            onClose={() => setReceiving(false)}
            order={current}
            onDone={() => {
              // A receipt moves stock in and books the payable: refresh both organs' reads.
              void qc.invalidateQueries({ queryKey: inventoryKeys.all });
              void qc.invalidateQueries({ queryKey: financeKeys.entries });
            }}
          />
          <PurchaseReceiptsList hooks={staffPurchasing} orderId={id} canWrite={isAdmin} />
        </>
      ) : null}
    </div>
  );
}

function PurchasingBody() {
  const { t } = usePageT();
  const isAdmin = useIsOrgAdmin();
  const [open, setOpen] = React.useState<Open>(null);
  const roster = staffTeam.useTeamRoster(isAdmin);
  const members = (roster.data ?? []).map((m) => ({ id: m.id, label: m.nome || m.email }));

  if (open !== null) return <OrderDetail id={open} onBack={() => setOpen(null)} />;
  return (
    <Tabs defaultValue="orders">
      <TabsList>
        <TabsTrigger value="orders">{t("admin.purchasing_tab_orders")}</TabsTrigger>
        <TabsTrigger value="receipts">{t("admin.purchasing_tab_receipts")}</TabsTrigger>
        {isAdmin ? <TabsTrigger value="approvers">{t("admin.purchasing_tab_approvers")}</TabsTrigger> : null}
      </TabsList>
      <TabsContent value="orders">
        <PurchaseOrdersTable hooks={staffPurchasing} canWrite={isAdmin} onNew={() => setOpen("new")} onOpen={(o) => setOpen(o.id)} />
      </TabsContent>
      <TabsContent value="receipts">
        <PurchaseReceiptsList hooks={staffPurchasing} canWrite={isAdmin} />
      </TabsContent>
      {isAdmin ? (
        <TabsContent value="approvers">
          <PurchaseApproversManager hooks={staffPurchasing} members={members} />
        </TabsContent>
      ) : null}
    </Tabs>
  );
}

export default function Compras() {
  return (
    <AdminFrame titleKey="admin.purchasing_title" introKey="admin.purchasing_intro">
      <PurchasingBody />
    </AdminFrame>
  );
}
