/**
 * RedirectToMeta — permanent redirect for the retired `/instagram-insights`
 * route (remodeled into the unified `/meta` dashboard, Wave 3).
 *
 * Mirrors `RedirectToMarcas.tsx`.
 */
import { Navigate } from "react-router-dom";

export default function RedirectToMeta() {
  return <Navigate to="/meta" replace />;
}
