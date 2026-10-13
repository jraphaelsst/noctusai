/**
 * `/pedido/:token` — public order view (organ `OrderStatusPage`: polls while
 * `pending_payment`, Pix QR + copy, hosted-checkout link, per-status copy,
 * 404 state). The expired-order "new payment" button stays disabled in P3
 * (`NOC-REMEDIATE[commerce-regenerate-payment]`, CONTRACT-DELTAS 9 → P4).
 */
import { useParams } from "react-router-dom";
import { OrderStatusPage } from "@noctusai/lib";

import { StorefrontFrame } from "@/components/StorefrontFrame";
import { storefrontCommerce } from "@/lib/commerce";

export default function StoreOrder() {
  const { token = "" } = useParams<{ token: string }>();
  return <StorefrontFrame>{() => <OrderStatusPage hooks={storefrontCommerce} token={token} />}</StorefrontFrame>;
}
