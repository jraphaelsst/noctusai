/**
 * `/checkout` — the organ `CheckoutForm` (buyer data, CPF/CNPJ check,
 * address only for shipped lines, payment method, Decreto 7.962 disclosures,
 * required consents + the immediate-delivery waiver for digital lines).
 * Success empties the cart and opens the public order view, which shows the
 * Pix QR / hosted-checkout link and polls the payment.
 */
import * as React from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { CheckoutForm, type CartApi } from "@noctusai/lib";
import { EmptyState } from "@noctusai/lib/design-system";

import { StorefrontFrame } from "@/components/StorefrontFrame";
import { storefrontCommerce } from "@/lib/commerce";
import { usePageT } from "@/lib/i18n";

function CheckoutBody({ cart }: { cart: CartApi }) {
  const { t } = usePageT();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const coupon = params.get("cupom") ?? "";
  const request = React.useMemo(
    () => ({ items: cart.quoteItems, ...(coupon ? { coupon } : {}) }),
    [cart.quoteItems, coupon],
  );

  if (cart.items.length === 0) {
    return (
      <div className="mx-auto max-w-xl space-y-3 text-center">
        <EmptyState message={t("store.cart_empty_checkout")} />
        <Link to="/" className="text-sm underline">
          {t("store.continue_shopping")}
        </Link>
      </div>
    );
  }
  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <h1 className="text-xl font-semibold">{t("store.checkout_title")}</h1>
      <CheckoutForm
        hooks={storefrontCommerce}
        request={request}
        onSuccess={(result) => {
          cart.clear();
          navigate(`/pedido/${encodeURIComponent(result.order_token)}`, { replace: true });
        }}
      />
    </div>
  );
}

export default function StoreCheckout() {
  return <StorefrontFrame>{(cart) => <CheckoutBody cart={cart} />}</StorefrontFrame>;
}
