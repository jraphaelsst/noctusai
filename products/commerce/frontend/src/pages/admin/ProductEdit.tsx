/**
 * `/admin/produtos/novo` and `/admin/produtos/:id` — the organ's
 * `ProductEditor` (fields, type slots, status transitions, media, delete) +
 * `OffersEditor` (prices + Asaas fee estimate). Create redirects to the new
 * product's own URL so offers and media can be added right away.
 */
import { Link, useNavigate, useParams } from "react-router-dom";
import { OffersEditor, ProductEditor } from "@noctusai/lib";

import { AdminFrame } from "@/components/AdminFrame";
import { staffCommerce } from "@/lib/commerce";
import { usePageT } from "@/lib/i18n";

function BackLink() {
  const { t } = usePageT();
  return (
    <Link to="/admin/produtos" className="text-sm underline-offset-4 hover:underline">
      {t("admin.back_to_products")}
    </Link>
  );
}

function OffersHint() {
  const { t } = usePageT();
  return <p className="text-sm text-muted-foreground">{t("admin.product_offers_hint")}</p>;
}

export default function ProductEdit() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const productId = id && id !== "novo" ? id : null;

  return (
    <AdminFrame titleKey={productId ? "admin.product_edit_title" : "admin.product_new_title"} actions={<BackLink />}>
      <ProductEditor
        key={productId ?? "new"}
        hooks={staffCommerce}
        productId={productId}
        onSaved={(p) => {
          if (!productId) navigate(`/admin/produtos/${p.id}`, { replace: true });
        }}
        onDeleted={() => navigate("/admin/produtos", { replace: true })}
      />
      {productId ? <OffersEditor hooks={staffCommerce} productId={productId} /> : <OffersHint />}
    </AdminFrame>
  );
}
