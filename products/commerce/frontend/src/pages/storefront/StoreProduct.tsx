/** `/p/:slug` — product page (organ `StorefrontProductPage`: media, offers, add to cart, 404 state). */
import { useNavigate, useParams } from "react-router-dom";
import { StorefrontProductPage } from "@noctusai/lib";

import { StorefrontFrame } from "@/components/StorefrontFrame";
import { storefrontCommerce } from "@/lib/commerce";

export default function StoreProduct() {
  const { slug = "" } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  return (
    <StorefrontFrame>
      {(cart) => (
        <StorefrontProductPage hooks={storefrontCommerce} slug={slug} cart={cart} onAdded={() => navigate("/carrinho")} />
      )}
    </StorefrontFrame>
  );
}
