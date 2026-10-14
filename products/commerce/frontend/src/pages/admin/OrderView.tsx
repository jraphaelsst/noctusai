/**
 * `/admin/pedidos/:id` — the organ's `OrderDetail` (items, totals, event
 * timeline, cancel transition) plus the buyer's fiscal snapshot
 * (CONTRACT-DELTAS A10: `buyer_name`, `buyer_doc` shown MASKED, and the
 * retention date). The buyer block reads the same `useOrder` query the organ
 * component uses — one request, shared cache.
 *
 * Below it the organ's `OrderMoneyPanel` (charges with parcelas, refunds incl. "em andamento", reminders,
 * invoices) with the refund / invoice actions for org admins only (UX; the server enforces). It reads the same
 * `useOrder` query — one request, shared cache.
 *
 * Named seam: the buyer block is a page-level addition next to the organ, not
 * a fork of it (see CONTRACT-DELTAS D5 — fold into `OrderDetail` upstream).
 */
import { Link, useParams } from "react-router-dom";
import { OrderDetail, OrderMoneyPanel, maskCpfOrCnpj, type Order } from "@noctusai/lib";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";

import { AdminFrame } from "@/components/AdminFrame";
import { staffCommerce } from "@/lib/commerce";
import { usePageT } from "@/lib/i18n";

/** A10 fields are not in the organ's `Order` type yet (D5). */
type OrderWithBuyer = Order & { buyer_name?: string | null; buyer_doc?: string | null; fiscal_retain_until?: string | null };

function BuyerSnapshot({ orderId }: { orderId: string }) {
  const { t, locale } = usePageT();
  const order = staffCommerce.useOrder(orderId);
  const o = order.data as OrderWithBuyer | undefined;
  // Loading / error / not-found are rendered by <OrderDetail/> below; this block only adds data when present.
  if (!o || (!o.buyer_name && !o.buyer_doc)) return null;
  return (
    <section className="rounded-md border p-3 text-sm" aria-label={t("admin.order_buyer")} data-testid="order-buyer">
      <h2 className="mb-1 font-semibold">{t("admin.order_buyer")}</h2>
      <dl className="grid gap-1 sm:grid-cols-3">
        <div>
          <dt className="text-xs text-muted-foreground">{t("admin.order_buyer_name")}</dt>
          <dd>{o.buyer_name || "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">{t("admin.order_buyer_doc")}</dt>
          <dd className="font-mono">{o.buyer_doc ? maskCpfOrCnpj(o.buyer_doc) : "—"}</dd>
        </div>
        {o.fiscal_retain_until ? (
          <div>
            <dt className="text-xs text-muted-foreground">{t("admin.order_fiscal_until")}</dt>
            <dd>{new Date(`${o.fiscal_retain_until}T00:00:00`).toLocaleDateString(locale)}</dd>
          </div>
        ) : null}
      </dl>
    </section>
  );
}

function MoneyPanel({ orderId }: { orderId: string }) {
  const isAdmin = useIsOrgAdmin();
  const order = staffCommerce.useOrder(orderId);
  // Loading / error / not-found are rendered by <OrderDetail/>; the money view only adds data when present.
  if (!order.data) return null;
  return <OrderMoneyPanel hooks={staffCommerce} order={order.data} isAdmin={isAdmin} />;
}

function BackLink() {
  const { t } = usePageT();
  return (
    <Link to="/admin/pedidos" className="text-sm underline-offset-4 hover:underline">
      {t("admin.back_to_orders")}
    </Link>
  );
}

export default function OrderView() {
  const { id = "" } = useParams<{ id: string }>();
  return (
    <AdminFrame titleKey="admin.order_title" actions={<BackLink />}>
      <BuyerSnapshot orderId={id} />
      <OrderDetail hooks={staffCommerce} orderId={id} />
      <MoneyPanel orderId={id} />
    </AdminFrame>
  );
}
