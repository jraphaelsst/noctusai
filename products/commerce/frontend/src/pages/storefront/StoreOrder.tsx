/**
 * `/pedido/:token` — public order view (organ `OrderStatusPage`: polls while
 * `pending_payment`, Pix QR + copy, hosted-checkout link, per-status copy,
 * 404 state). An expired / failed order offers "gerar novo pagamento" (the organ calls
 * `POST /api/storefront/orders/{token}/payment`; P4 closed `commerce-regenerate-payment`), and a
 * card order paid in parcelas shows what was charged.
 */
import { useParams } from "react-router-dom";
import { OrderStatusPage } from "@noctusai/lib";

import { StorefrontFrame } from "@/components/StorefrontFrame";
import { storefrontCommerce } from "@/lib/commerce";

export default function StoreOrder() {
  const { token = "" } = useParams<{ token: string }>();
  return <StorefrontFrame>{() => <OrderStatusPage hooks={storefrontCommerce} token={token} />}</StorefrontFrame>;
}
