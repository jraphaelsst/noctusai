/**
 * `/admin/produtos` — product list (search, status filter, pagination) with
 * "new product" and row → editor. Create / edit / status / delete / offers /
 * media happen in the editor page (`/admin/produtos/:id`), which composes the
 * organ's `ProductEditor` + `OffersEditor`.
 *
 * NOC-REMEDIATE[commerce-products-table-organ]: CONTRACT §5 ships no staff
 * product list component; this page-local list is the only one. Lift it into
 * the organ as `ProductsTable` before a second commerce product needs it
 * (CONTRACT-DELTAS D1).
 */
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { PRODUCT_STATUSES, type ProductStatus } from "@noctusai/lib";
import { Badge, Button, EmptyState, FormError, Input, Select, Skeleton } from "@noctusai/lib/design-system";

import { AdminFrame } from "@/components/AdminFrame";
import { staffCommerce } from "@/lib/commerce";
import { describeError, usePageT } from "@/lib/i18n";

function formatDate(iso: string | undefined, locale: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(locale);
}

function ProductsList() {
  const { t, locale } = usePageT();
  const navigate = useNavigate();
  const [q, setQ] = React.useState("");
  const [debounced, setDebounced] = React.useState("");
  const [status, setStatus] = React.useState<ProductStatus | "">("");
  const [page, setPage] = React.useState(1);

  React.useEffect(() => {
    const h = setTimeout(() => {
      setDebounced(q.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(h);
  }, [q]);

  const products = staffCommerce.useProducts({ q: debounced, status, page });

  if (products.showSkeleton) {
    return (
      <div className="space-y-2" data-testid="products-loading">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} height={36} width="100%" announce={i === 0} />
        ))}
      </div>
    );
  }
  if (products.isError && !products.data) {
    return (
      <div className="space-y-2">
        <FormError message={`${t("common.error_loading")}: ${describeError(products.error, t)}`} />
        <Button variant="outline" onClick={() => products.refetch()}>
          {t("common.retry")}
        </Button>
      </div>
    );
  }

  const rows = products.data?.data ?? [];
  const pg = products.data?.pagination;
  const totalPages = pg ? (pg.total_pages ?? Math.max(1, Math.ceil(pg.total / pg.page_size))) : 1;
  const filtered = !!debounced || !!status;

  return (
    <section className="space-y-3" aria-busy={products.isRefreshing}>
      <div className="flex flex-wrap gap-2">
        <div className="min-w-64 flex-1">
          <Input
            type="search"
            aria-label={t("admin.products_search")}
            placeholder={t("admin.products_search")}
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <Select
          aria-label={t("product.status")}
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as ProductStatus | "");
            setPage(1);
          }}
        >
          <option value="">{t("common.all")}</option>
          {PRODUCT_STATUSES.map((s) => (
            <option key={s} value={s}>
              {t(`product_status.${s}`)}
            </option>
          ))}
        </Select>
      </div>
      {products.isRefreshing ? (
        <p role="status" className="text-xs text-muted-foreground">
          {t("common.refreshing")}
        </p>
      ) : null}
      {rows.length === 0 ? (
        <EmptyState message={filtered ? t("admin.products_empty_search") : t("admin.products_empty")} />
      ) : (
        <table className="w-full text-sm" data-testid="products-table">
          <thead>
            <tr className="border-b text-left text-xs text-muted-foreground">
              <th className="p-2">{t("admin.products_col_title")}</th>
              <th className="p-2">{t("admin.products_col_type")}</th>
              <th className="p-2">{t("admin.products_col_status")}</th>
              <th className="p-2">{t("admin.products_col_updated")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr
                key={p.id}
                className="cursor-pointer border-b hover:bg-accent"
                onClick={() => navigate(`/admin/produtos/${p.id}`)}
              >
                <td className="p-2">
                  <span className="font-medium">{p.title}</span>{" "}
                  <span className="font-mono text-xs text-muted-foreground">/{p.slug}</span>
                </td>
                <td className="p-2">{t(`product_type.${p.product_type}`)}</td>
                <td className="p-2">
                  <Badge variant={p.status === "published" ? "default" : "outline"}>{t(`product_status.${p.status}`)}</Badge>
                </td>
                <td className="p-2">{formatDate(p.updated_at ?? p.created_at, locale)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {totalPages > 1 ? (
        <div className="flex items-center justify-end gap-2 text-sm">
          <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            {t("common.previous")}
          </Button>
          <span>
            {page} / {totalPages}
          </span>
          <Button size="sm" variant="outline" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
            {t("common.next")}
          </Button>
        </div>
      ) : null}
    </section>
  );
}

function NewProductButton() {
  const { t } = usePageT();
  const navigate = useNavigate();
  return <Button onClick={() => navigate("/admin/produtos/novo")}>{t("admin.products_new")}</Button>;
}

export default function Products() {
  return (
    <AdminFrame titleKey="admin.products_title" actions={<NewProductButton />}>
      <ProductsList />
    </AdminFrame>
  );
}
