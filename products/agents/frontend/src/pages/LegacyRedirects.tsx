/**
 * Pre-rename routes -> their new homes (2026-10-19: the Academia agent "Julia" is now "Bia",
 * and the SDR studio agent `lead-imob` is now "julia"). Old bookmarks and links keep working.
 *
 * NOC-REMEDIATE[drop-julia-route-redirects]: remove one release after the rename has shipped.
 */
import { Navigate, useLocation } from "react-router-dom";

function RedirectTo({ to }: { to: string }) {
  const { search, hash } = useLocation();
  return <Navigate to={`${to}${search}${hash}`} replace />;
}

/** `/julia` -> `/bia` */
export function RedirectJuliaToBia() {
  return <RedirectTo to="/bia" />;
}

/** `/agentes/julia/persona` -> `/agentes/bia/persona` */
export function RedirectJuliaPersonaToBia() {
  return <RedirectTo to="/agentes/bia/persona" />;
}

/** `/studio/lead-imob` -> `/studio/julia` */
export function RedirectLeadImobStudioToJulia() {
  return <RedirectTo to="/studio/julia" />;
}
