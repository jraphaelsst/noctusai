/**
 * `/minhas-compras` — without a token: the organ `MyOrdersRequest` (e-mail →
 * magic link, always 202, no enumeration). With `?token=` (the e-mailed
 * link, CONTRACT-DELTAS A1): the buyer's orders, each linking to its public
 * order view. An expired / tampered link says so and offers a new one.
 */
import { Link, useSearchParams } from "react-router-dom";
import { MyOrdersRequest, OrderStatusChip, formatCents } from "@noctusai/lib";
import { Button, EmptyState, FormError, Skeleton } from "@noctusai/lib/design-system";

import { StorefrontFrame } from "@/components/StorefrontFrame";
import { useMyOrders } from "@/hooks/useMyOrders";
import { storefrontCommerce } from "@/lib/commerce";
import { describeError, usePageT } from "@/lib/i18n";

function OrdersForToken({ token }: { token: string }) {
  const { t, locale } = usePageT();
  const orders = useMyOrders(token);

  if (orders.showSkeleton) {
    return (
      <div className="space-y-2" data-testid="myorders-loading">
        <Skeleton height={40} width="100%" />
        <Skeleton height={40} width="100%" announce={false} />
      </div>
    );
  }
  if (orders.isError && !orders.data) {
    return (
      <div className="space-y-3">
        <FormError message={describeError(orders.error, t)} />
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => orders.refetch()}>
            {t("common.retry")}
          </Button>
          <Link to="/minhas-compras" className="inline-flex items-center text-sm underline">
            {t("store.myorders_request_new")}
          </Link>
        </div>
      </div>
    );
  }
  const list = orders.data ?? [];
  return (
    <section className="space-y-3" aria-busy={orders.isRefreshing}>
      <h1 className="text-xl font-semibold">{t("store.myorders_list_title")}</h1>
      {list.length === 0 ? (
        <EmptyState message={t("store.myorders_empty")} />
      ) : (
        <ul className="divide-y rounded-md border" data-testid="myorders-list">
          {list.map((o) => (
            <li key={o.token} className="flex flex-wrap items-center justify-between gap-2 p-3 text-sm">
              <span className="flex items-center gap-2">
                <OrderStatusChip status={o.status} />
                {o.created_at ? new Date(o.created_at).toLocaleDateString(locale) : null}
                <span className="text-muted-foreground">{o.items.map((i) => `${i.qty}× ${i.title}`).join(", ")}</span>
              </span>
              <span className="flex items-center gap-3">
                <strong>{formatCents(o.total_cents, o.currency, locale)}</strong>
                <Link to={`/pedido/${encodeURIComponent(o.token)}`} className="underline">
                  {t("store.myorders_open")}
                </Link>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default function MyOrders() {
  const [params] = useSearchParams();
  const token = params.get("token");
  return (
    <StorefrontFrame>
      {() => (
        <div className="mx-auto max-w-2xl">
          {token ? <OrdersForToken token={token} /> : <MyOrdersRequest hooks={storefrontCommerce} />}
        </div>
      )}
    </StorefrontFrame>
  );
}
