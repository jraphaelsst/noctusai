/**
 * Storefront page frame: the organ's `<StorefrontShell/>` (store resolved from
 * the Host header, brand tokens, legal footer, locale) + the header actions
 * (cart count, "my orders") + ONE cart instance handed to the page.
 *
 * Back-office host (no store on this address): the shell renders its own
 * "no store here" state; a signed-in staff member is sent to `/admin`
 * (that is where the seed's SSO callback and login land them), anyone else
 * gets a discreet link to the staff login.
 */
import * as React from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { StorefrontShell, apiErrorStatus, useCart, type CartApi } from "@noctusai/lib";
import { useAuthStore } from "@noctusai/seed/infra";

import { storefrontCommerce } from "@/lib/commerce";
import { usePageT } from "@/lib/i18n";

function HeaderActions({ cart }: { cart: CartApi }) {
  const { t } = usePageT();
  return (
    <nav className="flex items-center gap-4 text-sm">
      <Link to="/privacidade" className="underline-offset-4 hover:underline">
        {t("store.privacy")}
      </Link>
      <Link to="/minhas-compras" className="underline-offset-4 hover:underline">
        {t("store.my_orders")}
      </Link>
      <Link
        to="/carrinho"
        className="rounded-md border px-3 py-1.5 font-medium"
        style={{ borderColor: "var(--commerce-primary, #4f46e5)", color: "var(--commerce-primary, #4f46e5)" }}
        data-testid="cart-link"
      >
        {t("store.cart_count", { count: cart.count })}
      </Link>
    </nav>
  );
}

function NoStoreHere() {
  const { user } = useAuthStore();
  const { t } = usePageT();
  if (user) return <Navigate to="/admin" replace />;
  return (
    <p className="pb-10 text-center text-xs text-muted-foreground">
      <Link to="/login" className="underline">
        {t("store.staff_link")}
      </Link>
    </p>
  );
}

export function StorefrontFrame({ children }: { children: (cart: CartApi) => React.ReactNode }) {
  const navigate = useNavigate();
  const cart = useCart();
  // Same query key as the shell's own read — shared cache, no second request.
  const storefront = storefrontCommerce.useStorefront();
  const noStore = !storefront.data && apiErrorStatus(storefront.error) === 404;

  return (
    <>
      <StorefrontShell hooks={storefrontCommerce} onHome={() => navigate("/")} headerActions={<HeaderActions cart={cart} />}>
        {children(cart)}
      </StorefrontShell>
      {noStore ? <NoStoreHere /> : null}
    </>
  );
}
