/** `/admin/pedidos` — order list (status filter, pagination) via the organ's `OrdersTable`. */
import { useNavigate } from "react-router-dom";
import { OrdersTable } from "@noctusai/lib";

import { AdminFrame } from "@/components/AdminFrame";
import { staffCommerce } from "@/lib/commerce";

export default function Orders() {
  const navigate = useNavigate();
  return (
    <AdminFrame titleKey="admin.orders_title">
      <OrdersTable hooks={staffCommerce} onSelect={(o) => navigate(`/admin/pedidos/${o.id}`)} />
    </AdminFrame>
  );
}
