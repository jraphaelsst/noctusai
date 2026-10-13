/**
 * `/carrinho` — the organ `Cart` (server quote, qty edits, coupon). Checkout
 * carries the coupon in the URL (`/checkout?cupom=`) so a reload of the
 * checkout page keeps it; the server re-quotes there anyway.
 */
import * as React from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Cart } from "@noctusai/lib";

import { StorefrontFrame } from "@/components/StorefrontFrame";
import { storefrontCommerce } from "@/lib/commerce";
import { usePageT } from "@/lib/i18n";

function ContinueShopping() {
  const { t } = usePageT();
  return (
    <Link to="/" className="text-sm underline-offset-4 hover:underline">
      {t("store.continue_shopping")}
    </Link>
  );
}

export default function StoreCart() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [coupon, setCoupon] = React.useState(params.get("cupom") ?? "");
  return (
    <StorefrontFrame>
      {(cart) => (
        <div className="mx-auto max-w-2xl space-y-4">
          <Cart
            hooks={storefrontCommerce}
            cart={cart}
            coupon={coupon}
            onCouponChange={setCoupon}
            onCheckout={() => navigate(coupon ? `/checkout?cupom=${encodeURIComponent(coupon)}` : "/checkout")}
          />
          <ContinueShopping />
        </div>
      )}
    </StorefrontFrame>
  );
}
