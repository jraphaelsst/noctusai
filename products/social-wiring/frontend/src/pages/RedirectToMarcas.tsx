/**
 * RedirectToMarcas — permanent redirect used to retire legacy routes.
 *
 * Routes retired (all → /clientes):
 *   /conexoes      (was: unified connections page)
 *   /conexao       (was: standalone WAHA-only page)
 *   /integrations  (was: back-compat alias for /conexoes)
 *
 * Connection management now lives inside MarcaModal (Contas tab).
 */
import { Navigate } from "react-router-dom";

export default function RedirectToMarcas() {
  return <Navigate to="/marcas" replace />;
}
