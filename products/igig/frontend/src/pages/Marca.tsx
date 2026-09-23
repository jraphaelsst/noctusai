/**
 * `/marca` — kept as a redirect only (wave-2 contract, Slice F).
 *
 * The Central da Marca moved into the cliente card (Clientes → card →
 * "Marcas"): a cliente carries N marcas, and the brand is edited where the
 * cliente lives (roadmap R9). The sidebar entry is gone; old links and
 * bookmarks land on the Clientes list instead of a 404.
 */
import { Navigate } from "react-router-dom";

export default function Marca() {
  return <Navigate to="/clientes" replace />;
}
