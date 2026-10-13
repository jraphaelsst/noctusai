/** `/` — the host-resolved storefront catalog (organ `ProductGrid`: search, pagination, empty/error states). */
import { useNavigate } from "react-router-dom";
import { ProductGrid } from "@noctusai/lib";

import { StorefrontFrame } from "@/components/StorefrontFrame";
import { storefrontCommerce } from "@/lib/commerce";

export default function StoreHome() {
  const navigate = useNavigate();
  return (
    <StorefrontFrame>
      {() => <ProductGrid hooks={storefrontCommerce} onOpen={(item) => navigate(`/p/${encodeURIComponent(item.slug)}`)} />}
    </StorefrontFrame>
  );
}
