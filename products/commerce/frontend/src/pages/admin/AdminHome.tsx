/** `/admin` — the back office opens on the orders list (where day-to-day work starts). */
import { Navigate } from "react-router-dom";

export default function AdminHome() {
  return <Navigate to="/admin/pedidos" replace />;
}
